"""fw private generate|run|retire: independent local corpus and frozen holdout evaluation."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import time

from eval.private_corpus import create,PROFILES,dump
from floorwise.paths import ROOT


def read(path):return json.loads(path.read_text(encoding='utf8'))


def verify(root):
    manifest=read(root/'manifest.json')
    from concurrent.futures import ThreadPoolExecutor
    def check(item):
        name,digest=item
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Manifest path escapes corpus root')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Private corpus checksum mismatch or missing case: '+name)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(check,manifest['hashes'].items()))
    if len({e['id'] for e in manifest['buildings']})!=len(manifest['buildings']):raise ValueError('Duplicate building IDs')
    minimum=PROFILES[manifest['profile']]
    if len(manifest['buildings'])<minimum or manifest['counts']['buildings']!=len(manifest['buildings']):raise ValueError('Required building coverage missing')
    if any(e['questions']<50 for e in manifest['buildings']) or manifest['counts']['questions']!=sum(e['questions'] for e in manifest['buildings']):raise ValueError('Question manifest count mismatch')
    if len(manifest['images'])<3*len(manifest['buildings']) or manifest['counts']['image_cases']!=len(manifest['images']):raise ValueError('Image manifest count mismatch')
    if len({c['id'] for c in manifest['images']})!=len(manifest['images']):raise ValueError('Duplicate image cases')
    return manifest


def route_verdict(row,reply,model):
    from eval import judge
    expected=row['expected'];line=reply.strip()
    if line.lower()=='no route':return not expected['reachable']
    if not expected['reachable']:return False
    sequence=judge.parse_answer(line)
    if not sequence:return False
    if row['inputs'].get('forklift') or row['inputs'].get('bays_are_destinations'):
        import copy
        from eval.private_oracle import graph
        _,allowed=graph(model.data,step_free=bool(row['inputs'].get('step_free')),closed={row['inputs']['closed']} if row['inputs'].get('closed') else set(),forklift=bool(row['inputs'].get('forklift')),bays=bool(row['inputs'].get('bays_are_destinations')),stops=row['stops'])
        model=copy.copy(model);model.graph=lambda step_free=False:allowed
    verdict=judge.measure(model,sequence,step_free=bool(row['inputs'].get('step_free')),closed={row['inputs']['closed']} if row['inputs'].get('closed') else set())
    # The judge measures a listed via-room door-to-door, whereas the reference
    # router visits its representative point. A shorter valid walk is not wrong.
    return bool(verdict.valid and judge.visits_in_order(sequence,row['stops']) and verdict.length_m is not None and verdict.length_m<=expected['length_m']*1.01+.01)


def evaluate_question(data,building,folder,row,kit):
    from floorwise.agent.solve import solve
    from floorwise.agent.answer import answer_with_trace,committed
    from floorwise.core import resolve
    from floorwise.agent.session import Session,Profile
    if row['layer']=='resolver_contract':
        expected=set(row['expected'])
        try:
            got=resolve.resolve_space(building,row['text']).id
            return {'correct':len(expected)==1 and got in expected,'observed':[got]}
        except resolve.ResolveError as error:
            got={c['id'] for c in error.candidates}
            return {'correct':not expected or (len(expected)>1 and got==expected),'observed':sorted(got),'clarification':bool(expected)}
    if row['layer']=='session_contract':
        i=row['inputs'];session=Session.for_building(building)
        session.profile=Profile(location=i['start'],step_free=i['step_free'],min_door_width_m=i['min_width'])
        session.closed.update(i['closed'])
        session.route('',i['first_destination'])
        result=session.route('',i['destination'])
        expected=row['expected'];valid=bool(result.get('error'))== (not expected['reachable'])
        if expected['reachable']:
            route=session.last_route
            valid=valid and route is not None and route.stops[0]==i['start'] and route.stops[-1]==i['destination'] and abs(route.length_m-expected['length_m'])<=.02
        valid=valid and session.profile.location==i['start'] and session.profile.step_free and session.profile.min_door_width_m==i['min_width']
        return {'correct':bool(valid),'observed':result.get('error') or {'from':result['from'],'to':result['to']},'scope':'typed session contract, not live language'}
    result,reply=solve(building,row['kind'],row['inputs'])
    text_reply,trace=answer_with_trace(folder,row['text'])
    if row['kind'] in ('route','tour'):
        solver_ok=route_verdict(row,committed(reply),kit)
        if row['expected']['reachable']:
            solver_ok=solver_ok and abs(result['length_m']-row['expected']['length_m'])<=.02
        text_ok=route_verdict(row,committed(text_reply),kit)
    else:
        keys={'count':'count','floor_area_total':'total_m2','straight_line_3d':'distance_m','wide_delivery_count':'count'}
        solver_ok=abs(result[keys[row['kind']]]-row['expected'])<=.02
        try:text_ok=abs(float(committed(text_reply))-row['expected'])<=.02
        except (ValueError,TypeError):text_ok=False
    return {'correct':bool(solver_ok and text_ok),'solver_correct':bool(solver_ok),'text_correct':bool(text_ok),
            'parser':trace.get('parser'),'fallback':trace.get('fallback'),'observed':committed(text_reply)}


def open_holdout(root,source):
    state_path=root/'lifecycle.json';state=read(state_path) if state_path.exists() else {}
    if state.get('retired'):raise ValueError('Holdout retired into regression coverage; generate a fresh corpus root')
    if state.get('holdout_source') and state['holdout_source']!=source:
        raise ValueError('Implementation changed after holdout use: retire it and generate a fresh corpus')
    state.update(holdout_source=source,holdout_last_run=time.time());dump(state_path,state)
    return state


def run(root,profile):
    os.environ['FLOORWISE_OFFLINE']='1'
    from eval.ledger import Ledger
    from eval.evidence import fingerprint
    from eval import judge
    from floorwise.core.model import Building
    from floorwise.agent.solve import solve
    from eval.private_oracle import moments
    from floorwise.build.builder import build
    from eval.build import translated,bounds
    from eval.reconstruction import measure,quality
    manifest=verify(root)
    lifecycle_path=root/'lifecycle.json';lifecycle=read(lifecycle_path) if lifecycle_path.exists() else {}
    if profile=='holdout':open_holdout(root,fingerprint()['source'])
    ledger=Ledger('private_'+profile,{'root':str(root),'manifest_sha256':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
                                    'generation':manifest['generation'],'profile':profile,'offline':True,'model_transport':'none'})
    selected=[e for e in manifest['buildings'] if (e['split']=='holdout' if profile=='holdout' else e['split']!='holdout' or lifecycle.get('retired'))]
    if profile=='smoke':selected=[e for e in selected if e['split']=='development'][:8]
    selected_ids={e['id'] for e in selected}
    expected_questions=sum(e['questions'] for e in selected);actual_questions=0
    tallies=defaultdict(Counter);unique_cases=set();image_hashes=set()
    # Independently derived analytic cases also check that the kit oracle agrees.
    for ref in read(root/'references.json'):
        b=Building(ref['data']);area,center=moments(ref['data']['spaces'][0]['polygon'])
        result,_=solve(b,'route',{'start':'A','destination':'B'})
        model=judge.kit_map(ref['data']);official=model.route('A','B')
        ok=area==ref['expected_area'] and list(center)==ref['expected_centroid'] and abs(result['length_m']-ref['expected_route_m'])<=.01 and abs(official.length_m-ref['expected_route_m'])<=.01
        ledger.record(id=ref['id'],kind='analytic reference',source='independent arithmetic',correct=ok)
    from eval.private_references import evaluate as analytic_checks
    for identifier,good in analytic_checks():
        ledger.record(id=identifier,kind='diverse analytic reference',source='independent arithmetic',correct=good)
    for entry in selected:
        folder=root/entry['path'];data=read(folder/'building.json');b=Building(data,folder);kit=judge.kit_map(data)
        rows=[json.loads(line) for line in (folder/'questions.jsonl').read_text(encoding='utf8').splitlines()]
        if len(rows)!=entry['questions']:raise ValueError('Required question count changed')
        for row in rows:
            actual_questions+=1
            unique_cases.add(hashlib.sha256(json.dumps({'building':b.id,'question':{k:v for k,v in row.items() if k!='id'}},sort_keys=True).encode()).hexdigest())
            try:out=evaluate_question(data,b,folder,row,kit)
            except Exception as error:out={'correct':False,'outcome':'error','error':f'{type(error).__name__}: {error}'}
            for key in ('solver_correct','text_correct'):
                if key in out:tallies[key]['total']+=1;tallies[key]['correct']+=out[key]
            ledger.record(id=row['id'],building=b.id,kind=row['kind'],layer=row['layer'],source=entry['family'],split=entry['split'],language_family=entry['language'],**out)
        if actual_questions%1000==0:print(f'Checked {actual_questions}/{expected_questions} private questions',flush=True)
    images=[c for c in manifest['images'] if c['building'] in selected_ids]
    for case in images:
        data=read(root/case['truth']);truth=data
        case_images={int(level):root/name for level,name in case['floor_images'].items()}
        image_hashes.update(manifest['hashes'][name] for name in case['floor_images'].values())
        try:
            if case['width_m'] is None:
                try:build(case_images,building_id='private-import')
                except ValueError as error:
                    out={'correct':'width' in str(error).lower() or 'scale' in str(error).lower(),'outcome':'clarification_required','automatic_reconstruction':False}
                else:out={'correct':False,'outcome':'invented_scale','automatic_reconstruction':False}
            else:
                predicted,report=build(case_images,width_m=case['width_m'],building_id='private-import')
                base_level=int(next(iter(case['floor_images'])))
                source_ids={f['id'] for f in truth['floors'] if f['level']==base_level};predicted_ids={f['id'] for f in predicted['floors'] if f['level']==base_level}
                x0,y0,_,_=bounds([s for s in truth['spaces'] if s['floor_id'] in source_ids]);px,py,_,_=bounds([s for s in predicted['spaces'] if s['floor_id'] in predicted_ids]);predicted=translated(predicted,x0-px,y0-py)
                metrics=measure(truth,predicted)
                geometric=quality(metrics,complete=True)
                auto=geometric and not report['review_required']
                out={'correct':auto,'geometry_correct':geometric,'automatic_reconstruction':auto,'review_required':report['review_required'],
                     'outcome':'passed' if auto else 'needs_review' if report['review_required'] else 'failed',
                     **{k:v for k,v in metrics.items() if not isinstance(v,(dict,list))}}
        except Exception as error:out={'correct':False,'outcome':'error','error':f'{type(error).__name__}: {error}'}
        ledger.record(id=case['id'],building=case['building'],kind='image '+case['difficulty'],source=case['family'],render_style=case['style'],split=case['split'],**out)
    coverage={'expected_questions':expected_questions,'evaluated_questions':actual_questions,'analytic_reference_checks':40,'unique_question_records':len(unique_cases),
              'buildings':len(selected),'expected_images':len(images),'evaluated_images':len(images),'unique_image_pixels':len(image_hashes),
              'families':dict(Counter(e['family'] for e in selected)),'layers':dict(tallies),
              'holdout_note':'Local frozen holdout; author can access it. Inspecting failures requires retirement before tuning.'}
    dump(ledger.directory/'coverage.json',coverage)
    result=ledger.finish()
    if len(unique_cases)!=actual_questions or actual_questions!=expected_questions or not result['total'] or result['correct']!=result['total'] or result.get('source_changed') or result.get('incomplete'):
        raise SystemExit('Private campaign failed quality or integrity checks; no failures were excluded')
    return result


def live(root,split,limit):
    """Bounded real LLM-parser evaluation, reported separately from offline coverage."""
    if not 1<=limit<=20:raise ValueError('Live private checks are bounded to 1-20 requests per process')
    os.environ.pop('FLOORWISE_OFFLINE',None)
    os.environ['FLOORWISE_MAX_TOKENS']=str(min(400000,int(os.environ.get('FLOORWISE_MAX_TOKENS','400000'))))
    from eval.ledger import Ledger
    from eval.evidence import fingerprint
    from eval import judge
    from floorwise import llm
    from floorwise.llm import budget
    from floorwise.agent import answer as benchmark
    if not llm.info().available:raise SystemExit('Private live evaluation incomplete: language provider unavailable')
    benchmark.USE_LLM=True
    manifest=verify(root)
    if split=='holdout':open_holdout(root,fingerprint()['source'])
    ledger=Ledger('private_live',{'generation':manifest['generation'],'split':split,'limit':limit,'max_tokens':int(os.environ['FLOORWISE_MAX_TOKENS']),'transport':'benchmark language path; models only for unknown wording'})
    entries=[e for e in manifest['buildings'] if e['split']==split][:limit]
    for i,e in enumerate(entries):
        folder=root/e['path'];data=read(folder/'building.json');kit=judge.kit_map(data)
        rows=[json.loads(line) for line in (folder/'questions.jsonl').read_text(encoding='utf8').splitlines()]
        row=next(r for r in rows if r['kind']=='route' and not r['inputs'].get('closed') and bool(r['inputs'].get('step_free'))==bool(i%2))
        try:
            before=budget.used()
            reply,trace=benchmark.answer_with_trace(folder,row['text'])
            spent=budget.used()-before
            ok=route_verdict(row,benchmark.committed(reply),kit)
            ledger.record(id=row['id'],building=e['id'],kind='live language',source=e['family'],correct=ok,parser=trace.get('parser'),fallback=trace.get('fallback'),reply=reply,total_tokens_delta=spent,usage=trace.get('usage',{}))
            ledger.add_usage({'total_tokens':spent})
        except Exception as error:
            ledger.record(id=row['id'],building=e['id'],kind='live language',source=e['family'],correct=False,outcome='error',error=f'{type(error).__name__}: {error}')
        print(f'Live private request {i+1}/{len(entries)} complete',flush=True)
    summary=ledger.finish()
    if len(entries)!=limit or summary['correct']!=summary['total'] or summary.get('source_changed'):
        raise SystemExit('Bounded private live evaluation failed; coverage is not inferred for untested requests')


def reissue(source,destination):
    """Reseal an unopened corpus after generator-only corrections; preserve old evidence."""
    import shutil
    from eval.private_corpus import questions
    manifest=verify(source)
    state=read(source/'lifecycle.json') if (source/'lifecycle.json').exists() else {}
    if state.get('holdout_source'):raise ValueError('Holdout already used; generate new geometry/seeds instead of resealing')
    if destination.exists():raise ValueError('Fresh corpus destination required')
    destination.mkdir(parents=True)
    from concurrent.futures import ThreadPoolExecutor
    def copy_file(name):
        if name.endswith('questions.jsonl'):return
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,target)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(copy_file,manifest['hashes']))
    for index,entry in enumerate(manifest['buildings']):
        folder=destination/entry['path'];data=read(folder/'building.json')
        rows=questions(data,manifest['seed']+index*100003,entry['language'])
        (folder/'questions.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in rows),encoding='utf8')
    manifest['parent_manifest_sha256']=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()
    manifest['generation']=__import__('secrets').token_hex(8)
    manifest['version']=2
    manifest['generator_sha256']=hashlib.sha256(Path(__file__).with_name('private_corpus.py').read_bytes()+Path(__file__).with_name('private_oracle.py').read_bytes()).hexdigest()
    from eval.private_corpus import checksums
    manifest['hashes']=checksums(sorted(p for p in destination.rglob('*') if p.is_file()),destination)
    dump(destination/'manifest.json',manifest)
    print('Resealed unopened corpus:',manifest['counts'],flush=True)
    return manifest


def main():
    cli=argparse.ArgumentParser(prog='fw private');subs=cli.add_subparsers(dest='action',required=True)
    g=subs.add_parser('generate');g.add_argument('--profile',choices=list(PROFILES),default='initial');g.add_argument('--root',type=Path);g.add_argument('--from-existing',type=Path)
    r=subs.add_parser('run');r.add_argument('--profile',choices=['smoke','full','holdout'],default='smoke');r.add_argument('--root',type=Path,default=ROOT/'runs/private-corpora/initial-v1')
    l=subs.add_parser('live');l.add_argument('--split',choices=['validation','holdout'],default='validation');l.add_argument('--limit',type=int,default=20);l.add_argument('--root',type=Path,default=ROOT/'runs/private-corpora/expanded-v2')
    t=subs.add_parser('retire');t.add_argument('--root',type=Path,default=ROOT/'runs/private-corpora/initial-v1')
    args=cli.parse_args();root=args.root or ROOT/f'runs/private-corpora/{args.profile}-v1'
    if args.action=='generate':
        resolved=root.resolve()
        if resolved.is_relative_to(ROOT.resolve()) and not resolved.is_relative_to((ROOT/'runs').resolve()):
            raise ValueError('Private data must live under gitignored runs/ or outside the repository')
        reissue(args.from_existing,root) if args.from_existing else create(root,args.profile)
    elif args.action=='run':run(root,args.profile)
    elif args.action=='live':live(root,args.split,args.limit)
    else:
        verify(root);state_path=root/'lifecycle.json';state=read(state_path) if state_path.exists() else {};state.update(retired=True,retired_at=time.time());dump(state_path,state)
        print('Holdout retired. Existing cases are regression data; generate a fresh corpus before another holdout claim.')


if __name__=='__main__':main()

"""Reconstruction v2: assisted floor diagnostics and the real whole-building importer.

Only a single known width enters build(); source JSON is consulted afterwards for
scoring. Historical build runs remain untouched. False openings/bridges are scored.
"""
import argparse
import copy
import json
import random
from pathlib import Path
from xml.sax.saxutils import escape

from shapely.affinity import translate
from eval.common import source_of, building_paths
from eval.ledger import Ledger
from eval.reconstruction import polygon, measure, quality
from floorwise.build.from_image import scan, to_building
from floorwise.build.builder import build
from floorwise.core.model import Building
from floorwise.paths import DATA


def floor_data(data, fid):
    return {'building':data.get('building',{}), 'floors':[f for f in data['floors'] if f['id']==fid],
            'spaces':[s for s in data['spaces'] if s['floor_id']==fid],
            'openings':[o for o in data['openings'] if o['floor_id']==fid], 'vertical_connectors':[], 'assets':[]}


def bounds(spaces):
    shapes=[polygon(s['polygon']) for s in spaces]
    if not shapes:
        raise ValueError('No recorded or detected spaces')
    return min(p.bounds[0] for p in shapes),min(p.bounds[1] for p in shapes),max(p.bounds[2] for p in shapes),max(p.bounds[3] for p in shapes)


def translated(data, dx, dy):
    out=copy.deepcopy(data)
    for s in out['spaces']:
        s['polygon']=[[x+dx,y+dy] for x,y in s['polygon']]
    for o in out['openings']:
        o['position']=[o['position'][0]+dx,o['position'][1]+dy]
    return out


def evaluate_floor(building, floor, image, return_models=False):
    """Explicitly assisted diagnostic; never a claim of autonomous import."""
    source=floor_data(building.data,floor['id'])
    detected=scan(image)
    if not detected.regions:
        raise ValueError('No rooms found in image')
    lo, bottom, hi, top=bounds(source['spaces'])
    xs=[x for r in detected.regions for x,y in r.polygon_px]
    ys=[y for r in detected.regions for x,y in r.polygon_px]
    scale=((hi-lo)/(max(xs)-min(xs))+(top-bottom)/(max(ys)-min(ys)))/2
    rebuilt=to_building([(floor['level'],detected)],scale,building_id='reconstructed')
    rebuilt=translated(rebuilt,lo-min(xs)*scale,top-(detected.height-min(ys))*scale)
    metrics=measure(source,rebuilt)
    metrics['calibration']='assisted true outline bounds; scoring diagnostic only'
    metrics['connected_share']=metrics['pairwise_reachability']  # old consumers: no outside-on-every-floor requirement
    return (metrics,source,rebuilt) if return_models else metrics


def pipeline_models(building, images):
    base=next(f for f in building.floors.values() if f['level']==next(iter(images)))
    base_source=floor_data(building.data,base['id'])
    x0,y0,x1,y1=bounds(base_source['spaces'])
    # This is a simulated caller-supplied real dimension, not a hidden coordinate transform.
    ordered={base['level']:images[base['level']],**{level:path for level,path in images.items() if level!=base['level']}}
    rebuilt,report=build(ordered,width_m=x1-x0,building_id='reconstructed',name='Evaluation draft')
    fid=next(f['id'] for f in rebuilt['floors'] if f['level']==base['level'])
    rx0,ry0,rx1,ry1=bounds(floor_data(rebuilt,fid)['spaces'])
    # Translation-only matching of arbitrary local coordinate origins, after import.
    rebuilt=translated(rebuilt,x0-rx0,y0-ry0)
    return rebuilt,report,x1-x0


def overlay(path,source,predicted,metrics):
    """Source outlines and reconstructed outlines in the same evaluated coordinate frame."""
    all_spaces=source['spaces']+predicted['spaces']
    if not all_spaces:return
    x0,y0,x1,y1=bounds(all_spaces);scale=900/max(x1-x0,y1-y0,1)
    def point(p):return f'{20+(p[0]-x0)*scale:.2f},{20+(y1-p[1])*scale:.2f}'
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="980" height="1040" viewBox="0 0 980 1040">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="20" y="970" font-size="16">Source: black/red (missing). Reconstruction: blue/orange (invented).</text>']
    matched=metrics['matched_spaces']
    for s in source['spaces']:
        color='#111' if s['id'] in matched else '#c8102e'
        parts.append(f'<polygon points="{" ".join(point(p) for p in s["polygon"])}" fill="none" stroke="{color}" stroke-width="2"/>')
    for s in predicted['spaces']:
        color='#0b5394' if s['id'] in matched.values() else '#c56c00'
        parts.append(f'<polygon points="{" ".join(point(p) for p in s["polygon"])}" fill="none" stroke="{color}" stroke-width="1" stroke-dasharray="5 3"/>')
    for data,color in [(source,'#c8102e'),(predicted,'#0b5394')]:
        for d in data['openings']:
            xy=point(d['position']).split(',');parts.append(f'<circle cx="{xy[0]}" cy="{xy[1]}" r="3" fill="{color}"/>')
    parts.append('</svg>');path.write_text(''.join(parts),encoding='utf8')


def checked_finish(ledger, threshold, complete=False):
    summary=ledger.finish()
    valid=bool(summary['total']) and summary['correct']==summary['total'] and not summary.get('source_changed') and not summary.get('incomplete')
    return valid


def main():
    cli=argparse.ArgumentParser(prog='eval.build')
    cli.add_argument('--split',default='dev');cli.add_argument('--limit',type=int,default=40)
    cli.add_argument('--recall-gate',type=float,default=.9)
    cli.add_argument('--mode',choices=['assisted','pipeline','both'],default='both')
    args=cli.parse_args()
    if not 0<args.recall_gate<=1:raise SystemExit('Quality threshold must be in (0,1]')
    config={'split':args.split,'mode':args.mode,'quality_threshold':args.recall_gate,'version':2,
            'width_provenance':'simulated caller measurement of base outline width'}
    assisted=Ledger('build_assisted',config) if args.mode in ('assisted','both') else None
    whole=Ledger('build',config) if args.mode in ('pipeline','both') else None
    floors_run=Ledger('build_pipeline_floor',config) if whole else None
    directories=building_paths([args.split], DATA);random.Random(3).shuffle(directories)
    for path in directories[:args.limit]:
        b=Building.load(path.parent);images={};missing=[]
        for floor in b.floors.values():
            image=path.parent/f"floor_{floor['level']}_plain.png"
            if not image.exists():missing.append(floor['id'])
            else:images[floor['level']]=image
            if assisted:
                try:
                    if not image.exists():raise ValueError('Required image missing')
                    metrics,source,predicted=evaluate_floor(b,floor,image,return_models=True)
                    ok=quality(metrics,args.recall_gate)
                    if not ok:overlay(assisted.directory/(floor['id']+'.svg'),source,predicted,metrics)
                    assisted.record(id=floor['id'],building=b.id,kind='assisted floor',source=source_of(b.id),correct=ok,**metrics)
                except Exception as error:
                    assisted.record(id=floor['id'],building=b.id,kind='assisted floor',source=source_of(b.id),correct=False,outcome='error',error=f'{type(error).__name__}: {error}')
        if whole:
            floor_rows=[]
            try:
                if missing:raise ValueError(f'Required images missing: {missing}')
                predicted,report,width=pipeline_models(b,images)
                metrics=measure(b.data,predicted)
                review=bool(report.get('review_required',False))
                whole_row=dict(id=b.id,building=b.id,kind='whole building',source=source_of(b.id),correct=quality(metrics,args.recall_gate,complete=True) and not review,review_required=review,import_report=report,supplied_width_m=width,**metrics)
                for floor in b.floors.values():
                    fid=next(f['id'] for f in predicted['floors'] if f['level']==floor['level'])
                    source=floor_data(b.data,floor['id']);got=floor_data(predicted,fid);fm=measure(source,got)
                    ok=quality(fm,args.recall_gate)
                    if not ok:overlay(floors_run.directory/(floor['id']+'.svg'),source,got,fm)
                    floor_rows.append(dict(id=floor['id'],building=b.id,kind='pipeline floor',source=source_of(b.id),correct=ok,**fm))
            except Exception as error:
                problem=f'{type(error).__name__}: {error}'
                whole_row=dict(id=b.id,building=b.id,kind='whole building',source=source_of(b.id),correct=False,outcome='error',error=problem)
                floor_rows=[dict(id=floor['id'],building=b.id,kind='pipeline floor',source=source_of(b.id),correct=False,outcome='error',error=problem) for floor in b.floors.values()]
            whole.record(**whole_row)
            for row in floor_rows:floors_run.record(**row)
        print('Assessed',b.id,flush=True)
    results=[checked_finish(r,args.recall_gate) for r in (assisted,whole,floors_run) if r]
    if not all(results):raise SystemExit('Reconstruction quality/integrity checks failed; raw failures and overlays retained.')


if __name__=='__main__':main()

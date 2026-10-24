"""Reproducible product profiles: fw test smoke|full|live|demo."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from eval.ledger import Ledger
from floorwise.paths import ROOT


def command(ledger, name, args, cwd=ROOT, env=None, record=True):
    print(f'PHASE {name}', flush=True)
    artifact = ledger.directory / (name + '.log')
    started = time.monotonic()
    with artifact.open('w', encoding='utf8') as log:
        process = subprocess.Popen(args, cwd=cwd, env=env or os.environ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf8', errors='replace')
        try:
            for line in process.stdout:
                log.write(line);log.flush();print(line.rstrip(), flush=True)
            code = process.wait()
        finally:
            if process.poll() is None: process.terminate()
    if record:
        ledger.record(id=name, kind=name, correct=code == 0, outcome='passed' if code == 0 else 'failed',
                      exit_code=code, seconds=round(time.monotonic()-started, 2), artifact=str(artifact.relative_to(ROOT)))
    if name in ('unit','browser'):
        child=Ledger(name,{'profile':ledger.config.get('profile'),'model_transport':'offline fixtures'})
        if name=='unit':
            import xml.etree.ElementTree as ET
            report=ledger.directory/'unit.xml'
            if report.exists():
                for case in ET.parse(report).iter('testcase'):
                    failed=case.find('failure');error=case.find('error');skipped=case.find('skipped')
                    issue=failed if failed is not None else error
                    child.record(id=case.get('classname','')+'::'+case.get('name',''),kind='unit',
                                 correct=issue is None and skipped is None,outcome='skipped' if skipped is not None else 'passed' if issue is None else 'failed',
                                 expected='assertions pass',observed=None if issue is None else (issue.text or '')[:12000])
        else:
            report=ledger.directory/'browser.json'
            if report.exists():
                data=json.loads(report.read_text(encoding='utf8'))
                def collect(suites):
                    for suite in suites:
                        yield from suite.get('specs',[])
                        yield from collect(suite.get('suites',[]))
                for spec in collect(data.get('suites',[])):
                    for test in spec.get('tests',[]):
                        results=test.get('results',[]);last=results[-1] if results else {}
                        status=last.get('status','incomplete')
                        child.record(id=spec.get('title','')+'::'+test.get('projectName',''),kind='browser',correct=status=='passed',outcome=status,
                                     observed=last.get('errors',[]),attachments=last.get('attachments',[]))
        if not child.rows:child.record(id=name,kind=name,correct=code==0,outcome='passed' if code==0 else 'failed',artifact=str(artifact.relative_to(ROOT)))
        child.finish()
        if name=='unit' and ledger.config.get('profile')=='full':
            for suite,tokens in [('submission',('test_submission','submission_contract')),('scenario',('test_evac','test_reason','explicit_scenario'))]:
                derived=Ledger(suite,{'profile':'full','layer':'deterministic unit contracts; browser evidence separate'})
                for row in child.rows:
                    if any(token in row['id'] for token in tokens):derived.record(**row)
                if not derived.rows:derived.record(id=suite,correct=False,outcome='incomplete',reason='No corresponding unit contracts collected')
                derived.finish()
    return code


def live(ledger, selected, selected_cases=None):
    from eval.conversations import cases
    catalog = [c for c in cases() if c['family'] == 'demo'] if selected == 'demo' else cases()
    if selected_cases:
        wanted=set(selected_cases)
        if wanted-{c['id'] for c in catalog}:raise ValueError('Unknown case ID')
        catalog=[c for c in catalog if c['id'] in wanted]
    node = __import__('shutil').which('node')
    if not node: raise RuntimeError('Node.js is required for the real-browser live pack')
    for batch_index in range(0, len(catalog), 10):
        batch = catalog[batch_index:batch_index+10]
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0));port=listener.getsockname()[1]
        token_budget=min(300000,int(os.environ.get('FLOORWISE_BATCH_TOKENS','300000')))
        env = dict(os.environ, FLOORWISE_EVAL_API='1', FLOORWISE_MAX_TOKENS=str(token_budget))
        env.pop('FLOORWISE_OFFLINE',None)
        log = (ledger.directory / f'server-{batch_index//10+1}.log').open('w', encoding='utf8')
        server = subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--port',str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(80):
                try:
                    urllib.request.urlopen(url+'/api/version', timeout=2);break
                except OSError:time.sleep(.25)
            manifest=ledger.directory/f'batch-{batch_index//10+1}.json'
            manifest.write_text(json.dumps({'cases':batch,'url':url,'tokenBudget':token_budget,'artifacts':str(ledger.directory.resolve())}),encoding='utf8')
            process=subprocess.Popen([node,str(ROOT/'web/tests/live-runner.cjs'),str(manifest.resolve())],cwd=ROOT/'web',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            completed=set()
            try:
                for line in process.stdout:
                    if line.startswith('FW_CASE '):
                        row=json.loads(line[8:]);completed.add(row['id']);ledger.record(**row);ledger.add_usage(row.get('usage',{}))
                        print(f"CASE {len(ledger.rows)}/{len(catalog)} {row['id']}: {row.get('outcome')} {row.get('reason','')}",flush=True)
                    else: print(line.rstrip(),flush=True)
                process.wait()
            finally:
                if process.poll() is None:process.terminate()
            for case in batch:
                if case['id'] not in completed:ledger.record(id=case['id'],kind=case['family'],correct=False,outcome='incomplete',reason='runner stopped before case completed')
        finally:
            server.terminate();server.wait(timeout=15);log.close()


def main():
    cli=argparse.ArgumentParser();cli.add_argument('profile',choices=['smoke','full','live','demo']);cli.add_argument('--case',action='append',dest='selected_cases');args=cli.parse_args()
    if args.selected_cases and args.profile not in ('live','demo'):cli.error('--case is only valid for live/demo profiles')
    ledger=Ledger('live_chat' if args.profile=='live' else args.profile,{'profile':args.profile,'transport':'real browser + SSE' if args.profile in ('live','demo') else 'offline fixtures'})
    py=sys.executable
    try:
        if args.profile in ('live','demo'):
            from floorwise.fw import web_is_stale
            if web_is_stale():
                if command(ledger,'build',[__import__('shutil').which('npm.cmd') or 'npm','run','build'],ROOT/'web',record=False):raise RuntimeError('Web build failed')
                # Build artifacts changed; capture the exact artifact tested below.
                from eval.evidence import fingerprint
                ledger.fingerprint=fingerprint()
            live(ledger,args.profile,args.selected_cases)
        else:
            env=dict(os.environ,FLOORWISE_OFFLINE='1')
            unit=[py,'-m','pytest','-q','--junitxml='+str((ledger.directory/'unit.xml').resolve())]
            if args.profile=='smoke':unit += ['tests/test_interactive_waits.py','tests/test_product_contracts.py','tests/test_nested_walk.py']
            command(ledger,'unit',unit,env=env)
            if args.profile=='full':
                for name,argv in [('gates',[py,'-u','-m','eval','gates']),('geometry_oracle',[py,'-u','-m','eval.geometry_oracle']),('walls',[py,'-u','-m','eval','walls','--split','train,dev,test','--pairs','4']),('import',[py,'-u','-m','eval','build','--split','dev','--limit','40'])]:command(ledger,name,argv,env=env)
            env['PLAYWRIGHT_JSON_OUTPUT_FILE']=str((ledger.directory/'browser.json').resolve())
            argv=[py,'-u','-m','floorwise.fw','ui-test','--reporter=json']
            if args.profile=='smoke':argv += ['product.spec.ts']
            command(ledger,'browser',argv,env=env)
    except Exception as error:
        ledger.record(id='profile_error',kind='infrastructure',correct=False,outcome='incomplete',reason=f'{type(error).__name__}: {error}')
    summary=ledger.finish()
    if summary['correct'] != summary['total']:raise SystemExit(1)


if __name__=='__main__':main()

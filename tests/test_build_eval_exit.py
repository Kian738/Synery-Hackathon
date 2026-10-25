"""A full release profile must not call a failed reconstruction phase successful."""
import sys
import inspect
from types import SimpleNamespace

import pytest

from eval import build


@pytest.mark.parametrize('good', [False, True])
def test_build_exit_reflects_floor_quality(monkeypatch, tmp_path, good):
    directory=tmp_path/'dev'/'fixture'
    directory.mkdir(parents=True)
    (directory/'building.json').write_text('{}')
    (directory/'floor_0_plain.png').write_bytes(b'fixture')
    monkeypatch.setattr(build,'DATA',tmp_path)
    monkeypatch.setattr(build.Building,'load',lambda _:SimpleNamespace(id='proc-campus-fixture',floors={'f':{'id':'f','level':0}}))
    metrics={k:1. for k in ('room_recall','room_precision','door_recall','door_precision','topology_recall','topology_precision','pairwise_reachability')}
    metrics['pairwise_reachability']=1. if good else .3
    whole_pipeline='return_models' in inspect.signature(build.evaluate_floor).parameters
    monkeypatch.setattr(build,'evaluate_floor',lambda *args,**kwargs:(metrics,{},{}) if whole_pipeline else {**metrics,'mean_iou':1.,'connected_share':1. if good else .3})
    if whole_pipeline:monkeypatch.setattr(build,'overlay',lambda *args:None)
    class Ledger:
        def __init__(self,*args):self.rows=[];self.directory=tmp_path;self.directory=tmp_path
        def record(self,**row):self.rows.append(row)
        def finish(self):return {'total':len(self.rows),'correct':sum(r['correct'] for r in self.rows)}
    monkeypatch.setattr(build,'Ledger',Ledger)
    monkeypatch.setattr(sys,'argv',['eval.build','--split','dev','--limit','1']+(['--mode','assisted'] if whole_pipeline else []))
    if good:
        build.main()
    else:
        with pytest.raises(SystemExit,match='(?i)reconstruction'):
            build.main()

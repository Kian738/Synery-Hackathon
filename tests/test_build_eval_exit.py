"""A full release profile must not call a failed reconstruction phase successful."""
import sys
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
    monkeypatch.setattr(build,'evaluate_floor',lambda *args:{'room_recall':1.,'door_recall':1.,'mean_iou':1.,'connected_share':1. if good else .3})
    class Ledger:
        def __init__(self,*args):self.rows=[]
        def record(self,**row):self.rows.append(row)
        def finish(self):return {'total':len(self.rows),'correct':sum(r['correct'] for r in self.rows)}
    monkeypatch.setattr(build,'Ledger',Ledger)
    monkeypatch.setattr(sys,'argv',['eval.build','--split','dev','--limit','1'])
    if good:
        build.main()
    else:
        with pytest.raises(SystemExit,match='reconstruction'):
            build.main()

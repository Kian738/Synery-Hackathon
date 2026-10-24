import json
from eval import ledger


def test_runs_in_same_second_never_overwrite_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(ledger,'RUNS',tmp_path)
    monkeypatch.setattr(ledger.time,'strftime',lambda _: 'same-second')
    monkeypatch.setattr(ledger,'git_sha',lambda: 'fixture')
    monkeypatch.setenv('FLOORWISE_OFFLINE','1')
    first=ledger.Ledger('parser',{'split':'train,dev'})
    second=ledger.Ledger('parser',{'split':'test'})
    for run in (first,second):
        run.record(correct=True,building='fixture',kind='parser')
        run.finish(quiet=True)
    assert first.directory!=second.directory
    assert json.loads((first.directory/'summary.json').read_text())['config']['split']=='train,dev'
    assert json.loads((second.directory/'summary.json').read_text())['config']['split']=='test'

import copy
import json
import pytest
from eval.private_corpus import make_building,questions,render,FAMILIES,STYLES,reference_scenarios
from eval.private_oracle import moments,route
from floorwise.build.from_image import scan
from floorwise.build.builder import build,link_cores
from floorwise.core.model import Building
from floorwise.agent.solve import solve
from eval import generated


def test_family_and_render_partitions_are_disjoint():
    for catalogue in (FAMILIES,STYLES):
        groups=[set(v) for v in catalogue.values()]
        assert all(not (a&b) for i,a in enumerate(groups) for b in groups[i+1:])


def test_new_buildings_are_reproducible_and_oracles_do_not_call_production(monkeypatch):
    b=make_building(2,'concave_branch',123)
    assert b==make_building(2,'concave_branch',123)
    monkeypatch.setattr('floorwise.agent.solve.solve',lambda *a,**k:pytest.fail('production solver used by oracle'))
    qs=questions(b,123,'canonical')
    assert len(qs)==50
    assert sum(q['layer']=='resolver_contract' for q in qs)==4
    assert any(q['expected']==[] for q in qs if q['kind']=='ambiguity')
    assert any(q['kind']=='context_correction' for q in qs)
    assert moments([[0,0],[4,0],[4,4],[0,4]])==(16.,(2.,2.))


def test_analytic_references_are_exact_for_both_implementations():
    from eval import judge
    refs=reference_scenarios();assert len(refs)==20
    for ref in refs:
        b=Building(ref['data']);result,_=solve(b,'route',{'start':'A','destination':'B'})
        independent=route(ref['data'],['A','B'])
        assert result['length_m']==independent['length_m']==ref['expected_route_m']
        assert moments(ref['data']['spaces'][0]['polygon'])[0]==ref['expected_area']


def test_no_real_scale_means_clarification_not_invented_default(tmp_path):
    with pytest.raises(ValueError,match='width'):
        build({0:tmp_path/'does-not-exist.png'})


def test_palette_shades_do_not_duplicate_rooms_and_dots_are_not_text(tmp_path):
    b=make_building(0,'spine',20)
    path=tmp_path/'plan.png';truth,width=render(b,path,'small_text',3)
    detected=scan(path)
    assert len(detected.regions)==len(truth['spaces'])
    assert len([m for m in detected.markers if m.kind=='door'])==len([o for o in truth['openings'] if 'outside' not in o['space_ids']])


def test_lifts_can_skip_stops_but_stairs_cannot():
    base=reference_scenarios()[0]['data']
    base['floors']=[{'id':'g','level':0},{'id':'u','level':2}]
    for kind in ('lift','stair'):
        data=copy.deepcopy(base);data['spaces']=[{**base['spaces'][0],'id':'lower','floor_id':'g','type':kind},{**base['spaces'][0],'id':'upper','floor_id':'u','type':kind}]
        data['vertical_connectors']=[];link_cores(data)
        assert bool(data['vertical_connectors'])==(kind=='lift')


def test_oracle_failure_is_never_a_no_route_result(monkeypatch):
    class Broken:
        closed=set()
        def route(self,*a,**k):raise RuntimeError('oracle is broken')
    with pytest.raises(RuntimeError):generated.oracle(Broken(),{'stops':['a','b']})


def test_literal_zero_inventory_count_does_not_need_a_present_type(monkeypatch,tmp_path):
    from floorwise.agent.spec import QuerySpec,resolve_spec
    b=Building(reference_scenarios()[0]['data'])
    inputs=resolve_spec(b,QuerySpec(kind='count',item='recorded test instrument',floor='Ground floor'))
    result,_=solve(b,'count',inputs)
    assert result['count']==0


def test_space_collection_suffix_is_resolved_without_changing_compound_types():
    from floorwise.core.resolve import resolve_room_type
    b=Building(reference_scenarios()[0]['data'])
    assert resolve_room_type(b,'office spaces')=='office'


def test_marker_recovery_is_resolution_aware(tmp_path):
    from PIL import Image
    b=make_building(0,'spine',20);path=tmp_path/'plan.png'
    truth,width=render(b,path,'flat',3)
    original=scan(path)
    with Image.open(path) as im:im.resize((im.width*2,im.height*2),Image.Resampling.NEAREST).save(tmp_path/'large.png')
    bigger=scan(tmp_path/'large.png')
    assert len(original.regions)==len(bigger.regions)
    assert len(original.markers)==len(bigger.markers)


def test_diverse_analytic_references_cover_vertical_outside_and_concavity():
    from eval.private_references import evaluate,cases
    rows=list(evaluate())
    assert len(rows)==20 and all(correct for _,correct in rows)
    assert len({c['id'].split('-')[0] for c in cases()})>=4


def test_official_building_cohort_comes_from_manifest(tmp_path):
    from eval.common import building_paths
    (tmp_path/'dev'/'official').mkdir(parents=True)
    (tmp_path/'dev'/'unlisted-experiment').mkdir(parents=True)
    (tmp_path/'dev'/'official'/'building.json').write_text('{}')
    (tmp_path/'dev'/'unlisted-experiment'/'building.json').write_text('{}')
    (tmp_path/'manifest.csv').write_text('building_id,split\nofficial,dev\n')
    assert building_paths(['dev'],tmp_path)==[tmp_path/'dev'/'official'/'building.json']
    (tmp_path/'dev'/'official'/'building.json').unlink()
    with pytest.raises(ValueError,match='missing'):building_paths(['dev'],tmp_path)


def test_private_requests_are_unique_per_building():
    b=make_building(0,'spine',40)
    rows=questions(b,40,'canonical')
    fingerprints={json.dumps({k:v for k,v in row.items() if k!='id'},sort_keys=True) for row in rows}
    assert len(rows)==len(fingerprints)==50


def test_industrial_corpus_includes_bay_and_forklift_rules():
    b=make_building(0,'spine',40,industrial=True)
    rows=questions(b,40,'canonical')
    assert any(r.get('inputs',{}).get('forklift') for r in rows)
    assert any(r.get('inputs',{}).get('bays_are_destinations') for r in rows)
    assert any(s['room_type']=='production_zone' for s in b['spaces'])


def test_holdout_cannot_follow_a_changed_implementation_without_retirement(tmp_path):
    from eval.private import open_holdout
    state=open_holdout(tmp_path,'source-a')
    assert state['holdout_source']=='source-a'
    open_holdout(tmp_path,'source-a')
    with pytest.raises(ValueError,match='changed'):open_holdout(tmp_path,'source-b')
    (tmp_path/'lifecycle.json').write_text(json.dumps({'retired':True}))
    with pytest.raises(ValueError,match='retired'):open_holdout(tmp_path,'source-a')


def test_checksum_mismatch_is_a_hard_error(tmp_path):
    from eval.private import verify
    from hashlib import sha256
    path=tmp_path/'case.json';path.write_text('original')
    (tmp_path/'manifest.json').write_text(json.dumps({'hashes':{'case.json':sha256(b'original').hexdigest()}}))
    path.write_text('modified')
    with pytest.raises(ValueError,match='checksum'):verify(tmp_path)


def test_changed_source_cannot_pass_finished_reconstruction():
    from eval.build import checked_finish
    class Changed:
        def finish(self):return {'total':1,'correct':1,'source_changed':True}
    assert not checked_finish(Changed(),.9)

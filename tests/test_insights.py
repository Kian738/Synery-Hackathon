import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from floorwise.agent.session import Session
from floorwise.agent.tools import make_tools
from floorwise.core.fixes import smallest_fix
from floorwise.core.graph import Constraints, RouteGraph
from floorwise.core.model import Building
from floorwise.core.resilience import chaos_test
from floorwise.paths import DATA
from server.app import app


@pytest.fixture
def factory():
    return Session.for_building(Building.load(DATA / 'dev' / 'proc-factory-dev-003'))


@pytest.fixture
def campus():
    return Session.for_building(Building.load(DATA / 'dev' / 'proc-campus-dev-000'))


def test_closure_reports_both_profiles_and_reopening(factory):
    impact = factory.set_closed('Office lift', True)['impact']
    assert impact['cut_off_count'] == 0
    assert impact['step_free']['cut_off_count'] == 29
    assert impact['step_free']['of_rooms'] == 56
    assert len(impact['step_free']['cut_off_ids']) == 29
    reopened = factory.set_closed('Office lift', False)['impact']
    assert len(reopened['step_free']['reconnected_ids']) == 29


def test_verified_trolley_fix_does_not_mutate_then_can_be_applied(campus):
    original = copy.deepcopy(campus.building.data)
    c = Constraints(step_free=True, min_width_m=1.1, outside='none')
    start, end = campus.space('Main lobby'), campus.space('Print room 0.16')
    fix = smallest_fix(campus.building, start, end, c)
    assert [w.opening_id for w in fix.widen] == ['proc-campus-dev-000-F0-O0015']
    assert fix.verified and (fix.widen[0].from_m, fix.widen[0].to_m) == (0.9, 1.1)
    assert campus.building.data == original
    result = campus.route(start, end, step_free=True, min_door_width_m=1.1)
    assert result['why']['verified'] and campus.events[-1]['type'] == 'fix_preview'
    campus.widen_door(fix.widen[0].opening_id, 1.1)
    assert 'error' not in campus.route(start, end, step_free=True, min_door_width_m=1.1)


def test_weak_points_are_exit_rooted_and_grouped(factory):
    r = chaos_test(factory.building, Constraints(step_free=True, outside='none'))
    assert r['rooms_reachable'] == 56
    assert r['critical'][0]['name'] == 'Office lift'
    assert r['critical'][0]['rooms_lost'] == 29
    assert max(item['rooms_lost'] for item in chaos_test(factory.building)['critical']) == 1


def test_no_width_fix_for_a_closed_lift(factory):
    a = next(s for s in factory.building.spaces if factory.building.level(factory.building.spaces[s]['floor_id']) == 0)
    b = next(s for s in factory.building.spaces if factory.building.level(factory.building.spaces[s]['floor_id']) == 1)
    lift = next(iter(factory.building.connectors.values()))['id']
    closed = frozenset(c['id'] for c in factory.building.connectors.values())
    assert not smallest_fix(factory.building, a, b, Constraints(step_free=True, min_width_m=1.1, closed=closed)).verified


def test_insight_tools_respect_read_only_mode(campus):
    names = {t.name for t in make_tools(campus, allow_edits=False)}
    assert {'count_items', 'distance_3d', 'shared_walls', 'errand', 'door_effect', 'weak_points'} <= names
    assert 'apply_fix' not in names


def test_insight_rest_routes():
    client = TestClient(app)
    sid = client.post('/api/sessions', json={'building_id': 'proc-campus-dev-000'}).json()['session_id']
    response = client.post(f'/api/sessions/{sid}/widen', json={'opening_id': 'proc-campus-dev-000-F0-O0015', 'width_m': 1.1})
    assert response.status_code == 200
    assert response.json()['events'][0]['type'] == 'edit'
    assert client.post(f'/api/sessions/{sid}/widen', json={'opening_id': 'missing', 'width_m': 1.1}).status_code == 422

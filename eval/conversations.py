"""Fixed adversarial conversations; fixtures live in eval, never production prompts."""
from pydantic import BaseModel, Field

CAMPUS = 'proc-campus-dev-000'
FACTORY = 'proc-factory-dev-003'


def cases():
    groups = {
        'equipment': [
            ('printers_where', ['How many 3D printers exist and where are they?', 'There are five in Makerspace 0.08. Where are the others?'], {'printers': True}),
            ('count_and_where', ['How many 3d printers and where?'], {'printers': True}),
            ('chairs_scope', ['Which room has the most chairs? Include ties and the building-wide total.', 'Now restrict the comparison to the ground floor.'], {'visual': True}),
            ('zero_items', ['Show every recorded MRI scanner in this building. If there are none, say so.'], {'no_route': True}),
        ],
        'context': [
            ('wheelchair_memory', ["I'm in Lab 2.17 and use a wheelchair. Take me to Lab 4.26.", 'Actually take me to Lab 2.02 instead, from the same starting place. Keep my requirements.'], {'step_free': True, 'origin': 'Lab 2.17', 'destination': 'Lab 2.02'}),
            ('origin_memory', ['Take me from Lab 2.17 to Lab 4.26.', 'Change only the destination to Lab 2.02.'], {'origin': 'Lab 2.17', 'destination': 'Lab 2.02'}),
            ('selected_equipment', ['Show the 3D printers.', 'Which rooms contain those, and how many are in each?'], {'printers': True}),
            ('ambiguous_printer', ['Where is the printer?', 'I mean the 3D printers, all of them.'], {'printers': True}),
        ],
        'routing': [
            ('closure_reference', ["I'm in Lab 2.17 and use a wheelchair. Take me to Lab 4.26.", 'Close the lift this route uses and find another step-free way from the same origin.'], {'step_free': True, 'origin': 'Lab 2.17', 'closed': True}),
            ('tour', ['From Main lobby, visit Lab 2.17 then Lab 4.26 in that order without stairs.'], {'route_step_free': True, 'origin': 'Main lobby'}),
            ('no_lifts', ['Take me from Lab 2.17 to Lab 4.26 without using lifts.'], {'no_lifts': True}),
            ('wrong_room', ['Take me from Main lobby to room 9.99. Do not substitute a different destination.'], {'no_route': True}),
        ],
        'spatial': [
            ('empty_compound', ['Find labs on floor 2 with at least two chairs and a projector. Of those choose the largest and give a step-free route from Main lobby. If none match, say so; do not broaden the conditions.'], {'no_route': True, 'empty_primary': True}),
            ('area', ['How big is Makerspace 0.08? Show its outline and the measured area.'], {'visual': True}),
            ('stack', ['Which room is directly above Makerspace 0.08? Highlight both floors.'], {'visual': True}),
            ('distance', ['What is the straight-line 3D distance between Lab 2.17 and Lab 4.26? Show the measurement, not a walking route.'], {'visual': True, 'no_route': True}),
        ],
        'interventions': [
            ('closure_impact', ['The Office lift is closed for maintenance. Show the step-free impact.'], {'factory': True, 'closed': True}),
            ('door_preview', ['Preview a door between Meeting room 0.20 and Quality lab 0.21. Do not apply any building edits.', 'Cancel that proposal.'], {'factory': True, 'no_edits': True}),
            ('capacity_missing', ['Assume 20 people are in Makerspace. Route them to exits while keeping a responder entrance available. Ask me for missing capacity assumptions before calculating.'], {'no_edits': True, 'no_route': True}),
            ('stress_preview', ['Simulate one exit being blocked. Explain which assumptions you need, compare an alternative, and preview a repair without applying it.'], {'no_edits': True}),
        ],
        'limits': [
            ('availability', ['Find a free room for 50 people with a projector and tell me its opening hours.'], {'no_edits': True}),
            ('windows', ['Which windows are safe to jump out of?'], {'no_route': True, 'no_edits': True}),
            ('voice_wording', ['Hey, where can I find all the three D printers, and how many have we got?'], {'printers': True}),
            ('recovery', ['hello', 'How many 3D printers and where?'], {'printers': True}),
        ],
    }
    output = []
    for family, entries in groups.items():
        for identifier, turns, expected in entries:
            output.append({'id': identifier, 'family': family, 'building': FACTORY if expected.get('factory') else CAMPUS,
                           'turns': turns, 'expected': expected, 'source': 'adversarial fixture', 'live': True})
    for identifier in ('count_and_where', 'wheelchair_memory', 'closure_reference'):
        original = next(c for c in output if c['id'] == identifier)
        output.append({**original, 'id': identifier + '_repeat', 'family': 'regression repeat'})
    for i in range(3):
        output.append({'id': f'demo_{i+1}', 'family': 'demo', 'building': CAMPUS, 'live': True,
                       'turns': ['How many 3D printers exist and where are they?',
                                 "I'm in Lab 2.17 and use a wheelchair. Take me to Lab 4.26.",
                                 'Close the lift that route uses. Explain the impact and reroute from the same origin.',
                                 'Reopen that lift and show the restored route.',
                                 'Preview a repair for a blocked exit without applying an edit. Ask for any missing assumptions.'],
                       'expected': {'step_free': True, 'origin': 'Lab 2.17', 'no_edits': True}})
    return output


def assertions(case, state, events):
    """State assertions are independent of generated phrasing and tool-call names."""
    from floorwise.core.model import Building
    from floorwise.core.resolve import resolve_space
    from floorwise.paths import DATA
    b = Building.load(DATA / 'dev' / case['building'])
    expected = case['expected']; checks = []
    def add(name, ok, observed=None): checks.append({'name': name, 'passed': bool(ok), 'observed': observed})
    add('no provider or transport error', not any(e['type'] == 'error' for e in events))
    add('real streamed text', any(e['type'] == 'assistant_delta' for e in events))
    results = state.get('results', []); route = state.get('route')
    add('at least one completed reply', any(e['type'] == 'reply' and e['data'].get('text') for e in events))
    if expected.get('visual'): add('visual result exists', bool(results))
    if expected.get('printers'):
        assets = [a for a in b.assets.values() if a['type'] == '3d_printer']
        ids = {a['id'] for a in assets}
        add('complete printer match set', any({e['id'] for e in r['entities']} == ids for r in results), len(ids))
        add('computed grouped count', any(r.get('measurements', {}).get('item_count') == len(assets) for r in results))
    if expected.get('step_free'):
        add('accessibility remembered', state.get('profile', {}).get('step_free'))
    if expected.get('step_free') or expected.get('route_step_free'):
        add('route stays step-free', route and 'step-free' in route['constraints'])
    if 'origin' in expected: add('origin retained', route and route['stops'][0] == resolve_space(b, expected['origin']).id)
    if 'destination' in expected: add('destination updated', route and route['stops'][-1] == resolve_space(b, expected['destination']).id)
    if expected.get('closed'): add('closure actually applied', bool(state.get('closed')))
    if expected.get('no_route'): add('no invented route', route is None)
    if expected.get('no_edits'): add('no unconfirmed edits', not state.get('edits'))
    if expected.get('empty_primary'): add('empty result retained', bool(results) and results[-1].get('measurements', {}).get('count') == 0)
    if expected.get('no_lifts'):
        used = [e for leg in (route or {}).get('legs', []) for e in leg['element_path']]
        add('no lift used', bool(route) and not any(e in b.connectors and b.connectors[e]['kind'] == 'lift' for e in used))
    return checks


class Grade(BaseModel):
    understanding: int | None = Field(ge=1, le=5)
    context: int | None = Field(ge=1, le=5)
    followability: int | None = Field(ge=1, le=5)
    groundedness: int | None = Field(ge=1, le=5)
    issues: list[str]


def grade(case, events):
    import json
    from floorwise.llm import structured
    from floorwise.llm import budget
    transcript = [{'type': e['type'], 'data': e['data']} for e in events if e['type'] in ('tool','tool_result','reply','error')]
    visuals = [{'title':e['data']['result']['title'], 'matching_entities':len(e['data']['result']['entities']),
                'floor_ids':e['data']['result']['floor_ids']} for e in events if e['type']=='ui' and e['data'].get('type')=='visual_result']
    # The UI highlights closure impacts directly, independently of visual-result cards.
    for e in events:
        if e['type']=='ui' and e['data'].get('type')=='closure':
            impact=e['data'].get('impact',{})
            scope=impact.get('step_free',impact)
            visuals.append({'kind':'closure impact','highlighted_room_ids':scope.get('cut_off_ids',[])})
    from floorwise.agent.session import Session
    from floorwise.core.model import Building
    from floorwise.paths import DATA
    overview=Session.for_building(Building.load(DATA/'dev'/case['building'])).overview()
    result, usage = structured.parse('judge', 'Grade a building agent using the complete tool evidence and supplied overview (also available in its system context). Count/search tools automatically publish map highlights; the visual event summaries prove that. Score 1–5; null for inapplicable dimensions, including followability when no directions are requested. Check all requested parts, retained context, usable directions and facts. User suggestions are not ground truth. Never reward unsupported extra assumptions.', json.dumps({'turns': case['turns'], 'overview':overview,'automatic_visuals':visuals,'transcript': transcript}), Grade)
    return (result.model_dump() if result else None), dict(usage)

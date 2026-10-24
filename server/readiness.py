"""Judge-aligned requirements and evidence. Historical success is never current proof."""
from eval.evidence import fingerprint, compatible

SOURCE = 'https://github.com/Synera-GmbH/industrial-agents-hackathon-2026'
REQUIREMENTS = [
    ('route_model', 'correctness', 'Exact routes and all route rules', 'routes', 1., 'README §3'),
    ('geometry', 'correctness', 'Exact areas, counts, stacking and boundaries', 'solver', 1., 'README §4'),
    ('benchmark', 'correctness', 'Answers from question text', 'e2e', .99, 'README §6'),
    ('submission', 'correctness', 'Sunday command and submission contract', 'submission', 1., 'README §6'),
    ('imports', 'correctness', 'Plan reconstruction and usable connectivity', 'build', 1., 'README levels 1–4'),
    ('conversation', 'interaction', 'Multi-turn factual and state contracts', 'live_chat', 1., 'Interaction rubric'),
    ('browser', 'interaction', 'Actual desktop and phone product flow', 'browser', 1., 'Interaction rubric'),
    ('walls', 'interaction', 'No emitted preview crosses rendered walls', 'walls', 1., 'Followable directions'),
    ('walk', 'interaction', 'Furniture clearance and preview availability', 'walkability', 1., 'Followable directions'),
    ('scenario', 'creativity', 'Computed closures, assumptions and interventions', 'scenario', 1., 'Level 5'),
    ('demo', 'demo', 'Three complete rehearsals without restart', 'demo', 1., 'Submission/demo'),
]
FEATURES = [
    ('chat', 'Conversational visual answers', 'Navigator → Ask the building', 'live_chat', 'implemented but unverified'),
    ('results', 'Room-grouped results and answer history', 'Chat → View results', 'browser', 'implemented but unverified'),
    ('guidance', 'Step-free multi-floor guidance', 'Room → Go here → Guide me', 'walls', 'implemented but unverified'),
    ('speeds', '0.5×, 1×, 2× and 4× playback', 'Guide me → Preview route', 'browser', 'implemented but unverified'),
    ('phone', 'Paired phone controller', 'Navigator → Phone', 'browser', 'implemented but unverified'),
    ('closures', 'Closure impact and rerouting', 'Tools → Stress test', 'live_chat', 'implemented but unverified'),
    ('import', 'Build from a floor plan', 'Navigator → Import plan', 'build', 'implemented but unverified'),
    ('evacuation', 'Capacity and responder scenarios', 'Tools → Scenarios', 'browser', 'implemented but unverified'),
    ('xr', 'AR/VR and live positioning', 'Outside this release', None, 'absent'),
]


DETAILS={
 'route_model':(['floorwise/core/graph.py','floorwise/core/spacewalk.py'],['tests/test_route_rules.py','eval/differential.py'],'Official distance semantics ignore furniture; human previews are checked separately.'),
 'geometry':(['floorwise/core/geometry.py','floorwise/core/ops.py'],['tests/test_geometry_oracle.py','eval/geometry_oracle.py'],'Independent area/centroid oracle plus gold and hand-computable geometry fixtures.'),
 'benchmark':(['floorwise/agent/answer.py','floorwise/agent/spec.py'],['eval/sunday.py','eval/e2e.py'],'Repeated room-name ambiguities remain raw misses; hidden-building grades are unknown.'),
 'submission':(['floorwise/submission.py','floorwise/cli.py'],['tests/test_submission_package.py'],'Complete public IDs and format validation do not prove hidden-answer correctness.'),
 'imports':(['floorwise/build/builder.py'],['eval/build.py','tests/test_build_eval_exit.py'],'Calibration and review assumptions are recorded; room, door and topology quality stay separate.'),
 'conversation':(['floorwise/agent/chat.py','server/app.py'],['eval/conversations.py','web/tests/live-runner.cjs'],'Model language review supplements deterministic assertions and is not human review.'),
 'browser':(['web/src/navigator/Navigator.tsx'],['web/tests/product.spec.ts','web/tests/navigator.spec.ts'],'Mocked model wording in offline UI tests; real provider behavior is measured by live_chat.'),
 'walls':(['floorwise/core/preview_check.py'],['eval/walls.py'],'Withheld/unavailable previews are not successful navigation.'),
 'walk':(['floorwise/core/walk.py'],['eval/walkability.py'],'Recorded furniture only; no physical tracking or claim of as-built safety.'),
 'scenario':(['floorwise/evacuation/solve.py','floorwise/agent/scenarios.py'],['tests/test_evac_invariants.py','web/tests/product.spec.ts'],'Hypothetical occupancy/rates must be explicit; unit solver contracts and visible UI evidence are separate.'),
 'demo':(['docs/DEMO.md'],['eval/conversations.py'],'Physical phone, projector and uncoached-human trials require people and hardware.')}


def readiness(summaries):
    current = fingerprint()
    requirements = []
    for identifier, group, title, suite, target, section in REQUIREMENTS:
        candidates = [s for s in summaries if s.get('suite') == suite]
        fresh = [s for s in candidates if compatible(s.get('fingerprint'), current)]
        latest = fresh[-1] if fresh else candidates[-1] if candidates else None
        state = ('untested' if not latest else 'historical' if not fresh else
                 'incomplete' if latest.get('incomplete') or latest.get('source_changed') else
                 'pass' if latest.get('accuracy', 0) is not None and latest.get('accuracy', 0) >= target else 'fail')
        if state=='pass' and latest.get('navigation') and (latest['navigation']['unavailable'] or latest['navigation']['withheld']):
            state='limited'
        requirements.append({'id': identifier, 'group': group, 'title': title, 'suite': suite, 'target': target,
                             'source': SOURCE, 'source_section': section, 'status': state, 'latest': latest,
                             'implementation':DETAILS[identifier][0], 'tests':DETAILS[identifier][1], 'assumptions':DETAILS[identifier][2]})
    return {'fingerprint': current,
            'groups': [{'id': k, 'title': title, 'points': points} for k, title, points in
                       [('correctness', 'Does it work?', 55), ('interaction', 'Interaction', 25),
                        ('creativity', 'Creativity', 10), ('demo', 'Pitch and demo', 10)]],
            'requirements': requirements, 'blockers': [r for r in requirements if r['status'] != 'pass'],
            'notice': 'Readiness evidence, not a predicted jury score. Raw misses remain misses.'}


def features(summaries):
    current = fingerprint()
    specific={'results':'equipment groups','speeds':'all four speeds','phone':'paired phone','evacuation':'scenario requires explicit',
              'closures':'closure_reference','chat':'printers_where','guidance':'route vs walls','import':'reconstruction'}
    def verified(identifier,suite):
        fresh=[s for s in summaries if s.get('suite')==suite and compatible(s.get('fingerprint'),current)
               and not s.get('incomplete') and not s.get('source_changed')]
        if not fresh:return False
        latest=fresh[-1]
        # A passing unrelated browser test or an old green run cannot verify this feature.
        token=specific.get(identifier,identifier).lower()
        return any(token in str(case).lower() for case in latest.get('coverage',{}).get('passed',[])) and not any(
            token in str(case).lower() for case in latest.get('coverage',{}).get('failed',[]))
    return [{'id': i, 'title': title, 'location': location, 'suite': suite,
             'status': 'verified and visible' if status == 'implemented but unverified' and verified(i,suite) else status,
             'backlog': 'docs/BACKLOG.md'} for i, title, location, suite, status in FEATURES]

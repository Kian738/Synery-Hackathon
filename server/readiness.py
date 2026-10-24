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
    ('closures', 'Closure impact and rerouting', 'Building tools → Stress test', 'scenario', 'implemented but unverified'),
    ('import', 'Build from a floor plan', 'Navigator → Import plan', 'build', 'implemented but unverified'),
    ('evacuation', 'Capacity and responder scenarios', 'Building tools → Scenarios', 'scenario', 'implemented but unverified'),
    ('xr', 'AR/VR and live positioning', 'Outside this release', None, 'absent'),
]


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
        requirements.append({'id': identifier, 'group': group, 'title': title, 'suite': suite, 'target': target,
                             'source': SOURCE, 'source_section': section, 'status': state, 'latest': latest})
    return {'fingerprint': current,
            'groups': [{'id': k, 'title': title, 'points': points} for k, title, points in
                       [('correctness', 'Does it work?', 55), ('interaction', 'Interaction', 25),
                        ('creativity', 'Creativity', 10), ('demo', 'Pitch and demo', 10)]],
            'requirements': requirements, 'blockers': [r for r in requirements if r['status'] != 'pass'],
            'notice': 'Readiness evidence, not a predicted jury score. Raw misses remain misses.'}


def features(summaries):
    current = fingerprint()
    return [{'id': i, 'title': title, 'location': location, 'suite': suite,
             'status': 'verified and visible' if status == 'implemented but unverified' and any(
                 s.get('suite') == suite and compatible(s.get('fingerprint'), current) and s.get('accuracy') == 1
                 and not s.get('incomplete') for s in summaries) else status,
             'backlog': 'docs/BACKLOG.md'} for i, title, location, suite, status in FEATURES]

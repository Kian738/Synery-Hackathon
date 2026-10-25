"""Bounded real-provider regression conversations; API/agent evidence, not browser evidence."""
import argparse
import time
from eval.ledger import Ledger
from floorwise.agent.chat import ChatAgent
from floorwise.agent.session import Session
from floorwise.core.model import Building
from floorwise.paths import DATA


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--building',default='proc-campus-dev-000');args=parser.parse_args()
    ledger=Ledger('chat_api',{'profile':'reported follow-up regressions','scope':'agent/provider only; visual acceptance unverified'})
    from floorwise import llm
    warm=time.perf_counter();llm.warm_provider();ledger.config['provider_warmup_seconds']=round(time.perf_counter()-warm,2)
    session=Session.for_building(Building.load(DATA/'dev'/args.building));agent=ChatAgent(session)
    prompts=['How many 3D printers exist and where are they?',
             'Which has the most in the whole building? vs in G',
             'Tell me for everything compact format',
             'Which room is directly above Makerspace 0.08? Show both floors.',
             'Now compare every item type in the whole building versus the ground floor.']
    for i,prompt in enumerate(prompts):
        events=[];start=time.perf_counter()
        try:
            reply=agent.ask(prompt,lambda kind,data:events.append({'type':kind,'data':data,'ms':round((time.perf_counter()-start)*1000)}))
            checks={'streamed_text':any(e['type']=='assistant_delta' for e in events),'reply':bool(reply)}
            if i==1:
                # A complete prior count already contains every room/floor; reuse is valid.
                counts=[v for v in session.visual_results.values() if v['kind']=='count']
                checks['complete_prior_evidence']=any(v['measurements'].get('count')==8 and
                    any(f['count']==5 for f in v['measurements'].get('per_floor',[])) for v in counts)
                checks['computed_leader']=any(v['measurements'].get('maximum_per_room')==5 and v['measurements'].get('top_tie_count')==1 for v in counts)
            if i in (2,4):checks['complete_comparison']=any(v['kind']=='comparison' and v['measurements'].get('scope_count')==2 for v in session.visual_results.values())
            if i in (2,4):
                tables=[v for v in session.visual_results.values() if v['kind']=='comparison']
                checks['all_item_types']=any(v['measurements'].get('type_count')==len({a['type'] for a in session.building.assets.values()}) for v in tables)
            ledger.record(id=f'follow_up_{i+1}',kind='provider conversation',correct=all(checks.values()),prompt=prompt,reply=reply,checks=checks,
                          events=events,usage=agent.turn_usage,first_text_ms=agent.turn_usage.get('first_text_ms'))
            ledger.add_usage({k:v for k,v in agent.turn_usage.items() if k.endswith('_tokens')})
            print(f'TURN {i+1}: {checks}, first text {agent.turn_usage.get("first_text_ms")} ms',flush=True)
        except Exception as error:ledger.record(id=f'follow_up_{i+1}',correct=False,prompt=prompt,error=f'{type(error).__name__}: {error}')
    summary=ledger.finish()
    if summary['correct']!=summary['total']:raise SystemExit(1)


if __name__=='__main__':main()

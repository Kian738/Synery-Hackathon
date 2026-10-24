"""Explicit hypothetical scenario inputs; no inferred occupancy or passage capacities."""
from floorwise.evacuation import Capacity, FlowParams, Hazard, Occupants, evacuate, to_dict, with_responders, Responders


def simulate(session, occupants, door_rate_per_minute, closed=(), responder_target=None, responder_entrance=None):
    if not occupants or any(isinstance(n,bool) or not isinstance(n,int) or n<0 for n in occupants.values()):
        raise ValueError('Supply explicit room occupancy as nonnegative whole people.')
    if sum(occupants.values())>1000 or len(occupants)>20:raise ValueError('Interactive scenarios support at most 1000 people in 20 rooms.')
    import math
    if not math.isfinite(door_rate_per_minute) or not 0<door_rate_per_minute<=10000:
        raise ValueError('Supply a positive assumed passage capacity in people per minute.')
    b=session.building
    people={}
    for mention,n in occupants.items():
        sid=session.place(mention);people[sid]=people.get(sid,0)+n
    blocked=tuple(session.element(x) for x in closed)
    blocked=tuple(set(blocked)|session.closed)
    spaces=tuple(x for x in blocked if x in b.spaces)
    elements=tuple(x for x in blocked if x not in b.spaces)
    params=FlowParams(max_horizon_s=300)
    caps=[Capacity(o,'rate_persons_per_s',door_rate_per_minute/60) for o in b.openings]
    population=Occupants.explicit(people)
    baseline=evacuate(b,population,capacities=caps,params=params,with_ccrp=False,with_nearest=False)
    hazard=Hazard(spaces=spaces,elements=elements)
    responder=None
    if responder_target:
        if not responder_entrance:raise ValueError('Choose the responder entrance explicitly.')
        entrance=session.element(responder_entrance)
        if entrance not in b.openings or 'outside' not in b.openings[entrance]['space_ids']:raise ValueError('Responder entrance must be a mapped exterior opening.')
        responder=with_responders(b,population,hazard,caps,params,responders=Responders(session.place(responder_target),entrances=(entrance,)))
        result=responder.evacuation if hasattr(responder,'evacuation') and responder.evacuation else evacuate(b,population,hazard,caps,params,with_ccrp=False,with_nearest=False)
    else:result=evacuate(b,population,hazard,caps,params,with_ccrp=False,with_nearest=False)
    assumptions=[f'User assumption: {door_rate_per_minute:g} people/minute for every mapped opening.',
                 'Explicit user occupancy only. No seating-capacity inference.',
                 'Scenario uses anchor-to-door distances and 5-second steps, with a 300-second horizon; not a walking preview.',*result.assumptions]
    ids=set(people)
    for move in result.schedule:
        if move.from_space in b.spaces:ids.add(move.from_space)
        if move.to_space in b.spaces:ids.add(move.to_space)
    lines=[]
    for move in result.schedule:
        if move.from_space not in b.spaces or move.to_space not in b.spaces:continue
        a,bp=b.polygons[move.from_space].representative_point(),b.polygons[move.to_space].representative_point()
        lines.append({'a':[a.x,a.y,b.elevation(b.spaces[move.from_space]['floor_id'])],
                      'b':[bp.x,bp.y,b.elevation(b.spaces[move.to_space]['floor_id'])]})
    rows=[{'id':sid,'label':b.label(sid),'count':n,'stranded':result.stranded.get(sid,0)} for sid,n in people.items()]
    visual=session.publish_visual('reachability',f'Scenario: {result.evacuated} of {population.total} evacuated',list(ids),
            {'evacuated':result.evacuated,'stranded':sum(result.stranded.values()),'clearance_s':result.T_s,
             'baseline_s':baseline.T_s,'baseline_evacuated':baseline.evacuated,'assumptions':assumptions,
             'method':'exact discrete-time capacity flow; responder search bounded to enumerated candidates' if responder else 'exact discrete-time capacity flow',
             'responder':to_dict(responder) if responder else None},rows,lines=lines,
            warnings=['Hypothetical scenario. Lines show aggregate model flow, not validated walking paths.'])
    return {'result_id':visual['id'],'total':population.total,'evacuated':result.evacuated,'stranded':sum(result.stranded.values()),
            'clearance_s':result.T_s,'baseline_s':baseline.T_s,'assumptions':assumptions,
            'responder':to_dict(responder) if responder else None}


def tools(session):
    from floorwise.llm.tools import tool
    from floorwise.agent.tools import guarded
    @tool
    def simulate_egress(occupants:dict[str,int],door_rate_per_minute:float,closed:list[str]=[],responder_target:str|None=None,responder_entrance:str|None=None)->str:
        """Hypothetical evacuation: explicit occupants by room and assumed people/minute per opening REQUIRED. Asks for missing inputs; does not infer occupancy. Optional closed passages/rooms, responder target and explicit mapped entrance. Publishes before/after metrics and schematic flow; never changes the building."""
        return guarded(simulate)(session,occupants,door_rate_per_minute,closed,responder_target,responder_entrance)
    @tool
    def reasoning_capabilities()->str:
        """List typed deterministic multi-step operators before constructing a reasoning plan."""
        import json
        from floorwise.reason import REGISTRY
        return json.dumps({'format':{'question':'text','steps':[{'id':'s1','op':'operator','args':{'world':'#world'}}],'answer':'#s1'},
                           'operators':[{'name':name,'params':[{'name':p.name,'type':p.type,'required':p.required} for p in REGISTRY.get(name).params],
                                         'returns':REGISTRY.get(name).returns,'description':REGISTRY.get(name).doc} for name in REGISTRY.names()]})
    @tool
    def run_reasoning_plan(plan:dict)->str:
        """Execute a typed multi-step deterministic plan; malformed plans abstain without mutating this session. Use reasoning_capabilities first."""
        from floorwise.reason import run_plan
        import dataclasses,json
        if len(plan.get('steps',[]))>30:raise ValueError('Use at most 30 reasoning steps in one interactive request.')
        result=run_plan(session.building,plan)
        from floorwise.reason.types import World
        answer=result.answer.summary() if isinstance(result.answer,World) else to_dict(result.answer)
        trace=[{'id':s.id,'operator':s.op,'ok':s.ok,'postconditions':s.checks,'summary':s.summary,'reason':s.reason,'ms':s.ms} for s in result.results]
        identifiers=set()
        def collect(value):
            if isinstance(value,str) and value in session.building.spaces:identifiers.add(value)
            elif isinstance(value,dict):
                for v in value.values():collect(v)
            elif isinstance(value,(list,tuple)):
                for v in value:collect(v)
        collect(answer)
        visual=None
        if identifiers:
            visual=session.publish_visual('matches','Computed multi-step answer',sorted(identifiers),{'steps':trace},
                [{'id':i,'label':session.building.label(i)} for i in sorted(identifiers)])
        return json.dumps({'answer':answer,'steps':trace,'abstained':dataclasses.asdict(result.abstained) if result.abstained else None,
                           'result_id':visual['id'] if visual else None},default=str)
    return [simulate_egress,reasoning_capabilities,run_reasoning_plan]

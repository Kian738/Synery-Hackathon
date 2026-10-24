"""Conservative, free chat dispatch. No benchmark shortcuts or model-computed facts."""
import re
import math

from floorwise.agent.parse_rules import FLOOR_NAME, parse_basic, parse_rules
from floorwise.core import geometry, ops, resolve


def _scope(text):
    match = re.search(rf'\s+(?:on|in)\s+(?:the\s+)?({FLOOR_NAME})$', text, re.I)
    return (text[:match.start()].strip(), match[1]) if match else (text, None)


def _clean(text):
    return re.sub(r'^(?:all|the|a|an)\s+', '', text.strip(), flags=re.I)


def _subject(session,mention):
    if mention.casefold().strip() not in ('it','this room','that room'):
        return mention
    selected=getattr(session,'ui_selection',None)
    if selected:return selected
    if session.visual_results:
        last=next(reversed(session.visual_results.values()))
        rooms=[e['id'] for e in last['entities'] if e['kind']=='room']
        if len(rooms)==1:return rooms[0]
    raise resolve.ResolveError('Which room do you mean?',[])


def dispatch(session, text):
    """None means unknown wording; ambiguity is deliberately raised for a clarification."""
    original=text
    text = text.strip().rstrip('?.!').strip()
    count_command=re.fullmatch(r'(?:count|give me (?:the )?(?:number|count) of|what(?: is|\x27s) the (?:total )?(?:number|count) of)\s+(.+)',text,re.I)
    if count_command:
        text='how many '+count_command[1]
    if re.search(r'jump.*window|window.*jump',text,re.I):
        return "I can guide you to mapped exits or stairs. I can't assess jumping safety."
    if re.search(r'\b(?:available|unbooked|bookings?|opening hours|staff.only|card access|seating capacity)\b',text,re.I) or re.search(r'\bfree (?:meeting )?rooms?\b',text,re.I):
        return 'Bookings, live availability, access rules and seating capacity are not supplied. I can find rooms by their recorded type, area and equipment.'
    # Do not partially execute multi-part requests or quietly ignore constraints.
    if re.search(r'\b(?:then|afterwards|except|excluding|but|avoid|without)\b', text, re.I):
        return None
    simple_route=re.fullmatch(r'(?:how (?:do|can) I (?:get|go|walk)|(?:guide|take) me)\s+from\s+(.+?)\s+to\s+(.+)',text,re.I)
    if simple_route and not re.search(r'\b(?:with|via|using|closed|blocked|prefer|wheelchair|step.free)\b',text,re.I):
        result=session.route(simple_route[1],simple_route[2])
        if result.get('error'):return result['error']
        return f"{result['from']} to {result['to']}: {result['length_m']} " + ('m walk. ' if result.get('walk_m') is not None else 'route-model m. ') + ' '.join(result['steps'])
    match = re.fullmatch(r'(?:which|what) (?:room|rooms) (?:has|have|contains?) (?:the )?most (.+)', text, re.I)
    if match:
        item, floor = _scope(match[1])
        result=session.rank_by_items(item, floor)
        if not result['rows']:
            return 'There are no matching rooms.'
        row=result['rows'][0]
        return f"{row['label']} has {row['count']} {item}, the highest count. {result['top_ties']} room(s) tie for first. Compared {result['total_rooms']} rooms; {result['total_items']} items total ({result['scope']})."
    match=re.fullmatch(r'how many (.+)',text,re.I)
    if match:
        item,floor=_scope(match[1])
        item=re.sub(r'\s+(?:items?\s+)?(?:are there|are|do we have|in (?:the |this )?building)$','',item,flags=re.I)
        item=re.sub(r'\s+items?$','',item,flags=re.I)
        if re.search(r'\b(?:rooms?|reachable|seats?|people|capacity)\b',item,re.I):
            return None
        result=session.count_items(_clean(item),floor)
        breakdown=', '.join(f"{r['label']}: {r['count']}" for r in result['per_floor'])
        return f"{result['count']} {_clean(item)} ({result['scope']}). {breakdown}. All matches are highlighted."
    match=re.fullmatch(r'(?:show(?: me)?|highlight|find) (.+)',text,re.I)
    if match:
        query,floor=_scope(match[1])
        compound=re.fullmatch(r'(.+?)\s+(?:with|containing)\s+(.+)',query,re.I)
        if compound:
            requirements=[]
            for phrase in re.split(r'\s+and\s+',compound[2],flags=re.I):
                req=re.fullmatch(r'(?:(?:at least )?(\d+)\s+)?(.+)',_clean(phrase),re.I)
                requirements.append({'item_type':_clean(req[2]),'minimum':int(req[1] or 1)})
            result=session.filter_rooms(requirements,floor,_clean(compound[1]))
            return f"{result['count']} rooms satisfy every requirement. All matching rooms are highlighted."
        if re.search(r'\b(?:and|or|nearest|free|available|largest|smallest)\b',query,re.I):
            return None
        result=session.search(_clean(query),floor)
        if not result["total"]:
            try:
                counted=session.count_items(_clean(query),floor)
                return f"{counted['count']} {_clean(query)}. All matches are highlighted."
            except resolve.ResolveError:
                return None
        return f"{result['total']} matches for {_clean(query)}. All matches are highlighted; the result list is paged."
    match=re.fullmatch(r'(?:how big is|what is the (?:size|area) of)\s+(.+)',text,re.I)
    if match:
        result=session.room_info(_subject(session,_clean(match[1])))
        return f"{result['name']} ({result['floor']}): {result['area_m2']} m², measured from its supplied polygon."
    match=re.fullmatch(r'where (?:is|are)\s+(?:the |a |an )?(.+)',text,re.I)
    if match:
        query,floor=_scope(match[1]);result=session.search(query,floor)
        labels=[r['label'] for r in result['spaces']]+[f"{r['name']} in {r['in']}" for r in result['assets']]
        if not labels:
            # Resolve known synonyms instead of claiming absence from a text-only search.
            try:
                result=session.count_items(query,floor)
                return f"{result['count']} {query}. All matches are highlighted."
            except resolve.ResolveError:
                return None
        return f"{result['total']} matches. " + '; '.join(labels[:4]) + ('. See all matches in the result list.' if result['total']>4 else '.')
    spec=parse_rules(original) or parse_basic(original)
    return execute_spec(session,spec) if spec else None


def execute_spec(session, spec):
    """Adapt parsed mentions to live-session operations; never use free outside hops for people."""
    b=session.building;kind=spec.kind
    if kind=='other':
        return None
    required={
        'largest_room':('floor','room_type'),'floor_area_total':('floor','room_type'),
        'errand':('start','floor','room_type'),'wide_delivery_count':('start','floor','min_width'),
        'step_free_reachable_count':('start','floor','closed'),'room_stacked':('start','direction'),
        'shared_walls_count':('start',),'straight_line_3d':('first','second'),
        'what_if_door':('first','second','floor'),'route':('destination',),
    }
    if any(getattr(spec,field) is None for field in required.get(kind,())):
        return None
    if kind in ('locate','count','errand') and not (spec.item or spec.asset_type):return None
    if kind=='tour' and (not spec.stops or len(spec.stops)<2):return None
    if spec.min_width is not None and (not math.isfinite(spec.min_width) or spec.min_width<=0):return None
    if kind=='locate':
        return dispatch(session,f'where is {spec.item or spec.asset_type}')
    if kind=='count':
        result=session.count_items(spec.item or spec.asset_type,spec.floor)
        return f"{result['count']} items ({result['scope']}). All matches are highlighted."
    if kind in ('route','tour','errand'):
        via=[]
        if kind=='tour':
            start,*middle,end=spec.stops;via=middle
        elif kind=='errand':
            # Nearest pickup uses live constraints, including closures and the person's needs.
            start=spec.start
            nearest=session.nearest(start,spec.asset_type or spec.item,step_free=True if spec.stairs_allowed is False else None)
            if not nearest.get('nearest'):
                return None
            via=[nearest['nearest'][0]['id']]
            end=ops.largest_room(b,resolve.resolve_floor(b,spec.floor),resolve.resolve_room_type(b,spec.room_type))['space_id']
        else:
            start,end=spec.start,spec.destination
        result=session.route(start,end,via,step_free=True if spec.step_free or spec.stairs_allowed is False else None,
                             min_door_width_m=spec.min_width,closed=[spec.closed] if spec.closed else None)
        if result.get('error'):
            return result['error']
        return f"{result['from']} to {result['to']}: {result['length_m']} {"m walk" if result.get('walk_m') is not None else "route-model m (walking preview unavailable)"}. " + ' '.join(result['steps'])
    if kind in ('largest_room','floor_area_total'):
        result=session.rank_rooms(spec.floor,spec.room_type)
        if kind=='floor_area_total':
            return f"{result['count']} rooms; total polygon area {result['total_area_m2']} m²."
        if not result['largest_first']:
            return 'There are no matching rooms.'
        row=result['largest_first'][0]
        return f"{row['name']} is largest at {row['area_m2']} m²."
    if kind=='room_stacked':
        sid=session.space(spec.start);result=ops.room_stacked(b,sid,spec.direction)
        if 'error' in result:
            return result['error']
        target=result['space_id']
        session.publish_visual('stacking',f'Room {spec.direction} {b.label(sid)}',[sid,target],result,
                               [{'id':target,'label':b.label(target),'overlap_m2':result['overlap_m2']}])
        return f"{b.label(target)} is {spec.direction}; {result['overlap_m2']} m² of polygon overlap."
    if kind in ('shared_walls_count','straight_line_3d','what_if_door'):
        from floorwise.agent.tools import make_tools
        import json
        tools={t.name:t for t in make_tools(session,allow_edits=False)}
        if kind=='shared_walls_count':
            result=json.loads(tools['shared_walls'].fn(room=spec.start))
            return f"{result['count']} rooms share a qualifying wall with {spec.start}."
        if kind=='straight_line_3d':
            result=json.loads(tools['distance_3d'].fn(room_a=spec.first,room_b=spec.second))
            return f"{result['distance_m']} m straight-line 3D distance; this is not a walking route."
        result=json.loads(tools['door_effect'].fn(room_a=spec.first,room_b=spec.second,on_floor=spec.floor))
        return f"{result['count']} rooms get a shorter route-model distance to an exit in this hypothetical edit."
    if kind in ('wide_delivery_count','step_free_reachable_count'):
        result=session.reachable(spec.start,spec.floor,step_free=True,min_door_width_m=spec.min_width,closed=[spec.closed] if spec.closed else None)
        return f"{result['reachable_rooms']} of {result['of_rooms_on_floor']} rooms are reachable under these constraints."
    return None

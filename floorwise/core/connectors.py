"""Complete connector inventory, separate from furniture and benchmark item counts."""
from collections import defaultdict
from shapely.geometry import Polygon
from floorwise.core import resolve


def connector_kind(mention):
    key=resolve.normalise(mention).strip()
    if key in {'stairs','stair','staircase','staircases','stairwell','stairwells','treppe','treppen'}:return 'stairs'
    if key in {'lift','lifts','elevator','elevators','aufzug','aufzüge'}:return 'lift'
    return None


def inventory(building,kind='stairs',floor=None,room=None):
    kind=connector_kind(kind)
    if kind is None:raise ValueError('Choose stairs or lifts. Individual stair treads are not surveyed.')
    fid=resolve.resolve_floor(building,floor) if floor else None
    sid=resolve.resolve_space(building,room).id if room else None
    target=building.spaces.get(sid)
    if target and fid is None:fid=target['floor_id']
    touching=defaultdict(list)
    for opening in building.openings.values():
        for at in opening['space_ids']:touching[at].append(opening)
    target_polygon=Polygon(target['polygon']) if target else None
    rows=[];ids=[];by_floor=defaultdict(set)
    for c in building.connectors.values():
        if c['kind']!=kind:continue
        stops=[]
        for sf,ss in zip(c['floor_ids'],c['space_ids']):
            if fid is not None and sf!=fid:continue
            if ss not in building.spaces:continue
            relation='mapped_stop'
            if target:
                if ss==sid:relation='same_space'
                elif any(sid in o['space_ids'] and o['floor_id']==sf for o in touching[ss]):relation='direct_opening'
                else:
                    poly=Polygon(building.spaces[ss]['polygon'])
                    if poly.area<=0 or not target_polygon.is_valid or not poly.is_valid or target_polygon.intersection(poly).area/poly.area<.5:continue
                    relation='inside_room_footprint'
            stops.append({'space_id':ss,'floor_id':sf,'relation':relation})
            by_floor[sf].add(c['id']);ids.append(ss)
        if stops:rows.append({'id':stops[0]['space_id'],'connector_id':c['id'],'label':c['name'],'floor_ids':[s['floor_id'] for s in stops],'stops':stops})
    return {'domain':'connectors','kind':kind,'count':len(rows),'scope':{'floor_id':fid,'room_id':sid,'room':building.label(sid) if sid else None},
            'count_basis':'distinct mapped connector records, not individual steps or inferred continuous staircases',
            'individual_step_count':None,'rows':rows,'ids':list(dict.fromkeys(ids)),
            'per_floor':[{'id':f['id'],'label':f['name'],'count':len(by_floor[f['id']])} for f in sorted(building.floors.values(),key=lambda f:f['level']) if fid is None or fid==f['id']],
            'warning':'Room scope counts mapped stops in or directly opening into that room on its floor. Adjacent stairwell walls alone do not establish access.'}

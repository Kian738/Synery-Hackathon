"""Private-corpus expectations: pure arithmetic plus the independent kit router.
Never imports Floorwise geometry, routing, solving or parsing to create expectations.
"""
import copy
import math
import networkx as nx


def moments(points):
    twice=mx=my=0.
    for a,b in zip(points,[*points[1:],points[0]]):
        cross=a[0]*b[1]-b[0]*a[1];twice+=cross;mx+=(a[0]+b[0])*cross;my+=(a[1]+b[1])*cross
    if abs(twice)<1e-10:raise ValueError('Degenerate source polygon')
    return abs(twice)/2,(mx/(3*twice),my/(3*twice))


def graph(data,step_free=False,closed=(),width=0.,forklift=False,bays=False,stops=()):
    # Imported here to make the data generator usable without production modules.
    from floorwise.paths import use_kit_modules
    use_kit_modules()
    from starter_agent.building_map import BuildingMap
    model=BuildingMap(copy.deepcopy(data))
    if forklift:width=max(width,3.)
    model.closed=set(closed)|{o['id'] for o in data['openings'] if o.get('width_m',0)<width}
    terminal=set(stops)
    for space in data['spaces']:
        is_bay=space['type']=='hall' and space['room_type'].endswith('_zone')
        if bays and is_bay and space['id'] not in terminal:model.closed.add(space['id'])
        if forklift and space['id'] not in terminal:
            from shapely.geometry import Polygon
            admissible=space['type'] in ('corridor','hall','outdoor') and not is_bay and not Polygon(space['polygon']).buffer(-1.5).is_empty
            if not admissible:model.closed.add(space['id'])
    if forklift:model.closed.update(c['id'] for c in data['vertical_connectors'])
    return model,model.graph(step_free)


def route(data,stops,step_free=False,closed=(),width=0.,prepared=None):
    model,g=prepared if prepared is not None else graph(data,step_free,closed,width)
    nodes=[];length=0.
    for a,b in zip(stops,stops[1:]):
        try:distance,part=nx.single_source_dijkstra(g,a,b,weight='weight')
        except nx.NetworkXNoPath:return {'reachable':False,'length_m':None,'route':None}
        except nx.NodeNotFound:
            # A closure can remove a valid source stop; unknown IDs are errors.
            ids={s['id'] for s in data['spaces']}
            if a not in ids or b not in ids:raise
            return {'reachable':False,'length_m':None,'route':None}
        nodes.extend(part if not nodes else part[1:]);length+=distance
    spaces=[n for n in nodes if not n.startswith('door:')]
    spaces=[s for i,s in enumerate(spaces) if not i or spaces[i-1]!=s]
    return {'reachable':True,'length_m':round(length,2),'route':spaces}


def numeric(data,kind,inputs):
    spaces={s['id']:s for s in data['spaces']}
    if kind=='count':return sum(a['type']==inputs['asset_type'] and a['floor_id']==inputs['floor_id'] for a in data['assets'])
    if kind=='floor_area_total':return round(sum(moments(s['polygon'])[0] for s in spaces.values() if s['floor_id']==inputs['floor_id'] and s['room_type']==inputs['room_type']),2)
    if kind=='straight_line_3d':
        levels={f['id']:f['elevation_m'] for f in data['floors']}
        points=[]
        for key in ('first','second'):
            s=spaces[inputs[key]];_,xy=moments(s['polygon']);points.append((*xy,levels[s['floor_id']]))
        return round(math.dist(*points),2)
    if kind=='wide_delivery_count':
        _,g=graph(data,True,width=inputs['min_width'])
        reached=nx.node_connected_component(g,inputs['start']) if inputs['start'] in g else set()
        return sum(s['id'] in reached and s['floor_id']==inputs['floor_id'] and s['type']=='room' for s in spaces.values())
    raise ValueError('Unimplemented independent oracle kind: '+kind)

"""Display/walking repair for enclosed spaces nested inside a larger circulation polygon.

Benchmark polygons/distances stay unchanged. A hallway's overlapping outline is not
permission to walk through a separately recorded room or stairwell's walls.
"""
import heapq
import math
from functools import lru_cache

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union


@lru_cache(maxsize=2048)
def nested_spaces(building, space_id):
    outer = building.polygons[space_id]
    floor = building.spaces[space_id]['floor_id']
    return [poly for sid, poly in building.polygons.items()
            if sid != space_id and building.spaces[sid]['floor_id'] == floor
            and building.spaces[sid]['type'] != 'corridor'
            and .02 < poly.area < outer.area * .95
            and outer.intersection(poly).area >= poly.area * .995]


def repair_nested_crossings(building, space_id, points, a_door=True, b_door=True):
    if len(points) < 2:
        return points
    obstacles = nested_spaces(building, space_id)
    if not obstacles or all(LineString(points).intersection(p.buffer(-.01)).length <= .01 for p in obstacles):
        return points
    free = building.polygons[space_id].buffer(-.15, join_style='mitre').difference(
        unary_union(obstacles).buffer(.15, join_style='mitre'))
    # Preserve equipment clearance too; a wall repair must not introduce a table collision.
    assets = []
    for asset in building.assets.values():
        if asset['space_id'] != space_id or asset.get('category') not in {'furniture','machine','equipment','fixture'}:
            continue
        f=asset.get('footprint') or {};w=f.get('width_m',.5);d=f.get('depth_m',.5)
        a=math.radians(f.get('rotation_deg',0));x,y=asset['position']
        assets.append(Polygon([(x+u*math.cos(a)-v*math.sin(a),y+u*math.sin(a)+v*math.cos(a))
                              for u,v in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]]).buffer(.2,join_style='mitre'))
    if assets:
        free=free.difference(unary_union(assets))
    if free.is_empty:
        raise ValueError('Nested enclosure leaves no walking passage')
    def snap(p):
        return tuple(nearest_points(free,Point(p))[0].coords)[0] if not free.covers(Point(p)) else tuple(p)
    start,end=snap(points[0]),snap(points[-1])
    polygons=[p for p in getattr(free,'geoms',[free]) if p.geom_type=='Polygon']
    nodes=[start,end]+[tuple(c) for p in polygons for ring in [p.exterior,*p.interiors] for c in list(ring.coords)[:-1]]
    if len(nodes)>2400:
        raise ValueError('Nested enclosure walking geometry is too complex')
    xy=np.array(nodes);i,j=np.triu_indices(len(nodes),1)
    segments=shapely.linestrings(np.stack((xy[i],xy[j]),axis=1))
    clear=shapely.covers(free.buffer(.002),segments)
    adjacency=[[] for _ in nodes]
    for u,v in zip(i[clear],j[clear]):
        cost=math.dist(nodes[u],nodes[v]);adjacency[u].append((v,cost));adjacency[v].append((u,cost))
    dist={0:0.};parent={};queue=[(0.,0)]
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=dist[u]:continue
        if u==1:break
        for v,length in adjacency[u]:
            candidate=cost+length
            if candidate<dist.get(v,float('inf')):
                dist[v]=candidate;parent[v]=u;heapq.heappush(queue,(candidate,v))
    if 1 not in dist:
        raise ValueError('No passage around nested enclosure')
    chain=[1]
    while chain[-1]!=0:chain.append(parent[chain[-1]])
    result=[nodes[k] for k in reversed(chain)]
    if a_door and tuple(points[0])!=start:result.insert(0,tuple(points[0]))
    if b_door and tuple(points[-1])!=end:result.append(tuple(points[-1]))
    if any(LineString(result).intersection(p.buffer(-.01)).length>.01 for p in obstacles):
        raise ValueError('Endpoint crosses an enclosed space')
    return result

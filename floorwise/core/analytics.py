"""Complete, deterministic chat analytics. Benchmark operators retain their exact semantics."""
from collections import Counter, defaultdict

from floorwise.core import resolve


def item_leaders(building, floor=None, compare_floor=None):
    """One pass over assets, complete exact-type totals and every tied leading place."""
    scopes=[resolve.resolve_floor(building,floor) if floor else None]
    if compare_floor is not None:scopes.append(resolve.resolve_floor(building,compare_floor))
    records=[]
    for fid in scopes:
        counts=defaultdict(Counter)
        for asset in building.assets.values():
            if fid is None or asset['floor_id']==fid:counts[asset['type']][asset['space_id']]+=1
        records.append((fid,counts))
    rows=[]
    for kind in sorted({a['type'] for a in building.assets.values()}):
        summaries=[]
        for fid,counts in records:
            grouped=counts.get(kind,Counter());maximum=max(grouped.values(),default=0)
            ids=sorted((sid for sid,n in grouped.items() if n==maximum),key=building.label)
            summaries.append({'scope':building.floor_name(fid) if fid else 'Whole building',
                              'total':sum(grouped.values()),'maximum':maximum,'leader_ids':ids,
                              'leaders':[building.label(sid) for sid in ids]})
        rows.append({'id':summaries[0]['leader_ids'][0] if summaries[0]['leader_ids'] else kind,
                     'label':kind.replace('_',' '),'item_type':kind,'scopes':summaries,'count':summaries[0]['maximum']})
    return {'rows':rows,'type_count':len(rows),'scope_count':len(records),'semantics':'exact recorded types; all tied places; counts are not seating capacity'}


def asset_kinds(building, mention: str, inclusive: bool = True) -> list[str]:
    key = resolve.normalise(mention).strip()
    if inclusive and key in {"chair", "chairs"}:
        return sorted({a['type'] for a in building.assets.values()
                       if 'chair' in a['type'].split('_') or a['type'] == 'armchair'})
    return [resolve.resolve_asset_type(building, mention)]


def rooms(building, floor=None, room_type=None):
    fid = resolve.resolve_floor(building, floor) if floor else None
    kind = resolve.resolve_room_type(building, room_type) if room_type else None
    return [s for s in building.spaces.values() if building.is_room(s['id'])
            and (fid is None or s['floor_id'] == fid) and (kind is None or s['room_type'] == kind)]


def count_items(building, item_type, floor=None, room=None, inclusive=True):
    kinds = asset_kinds(building, item_type, inclusive)
    fid = resolve.resolve_floor(building, floor) if floor else None
    sid = resolve.resolve_space(building, room).id if room else None
    items = [a for a in building.assets.values() if a['type'] in kinds
             and (fid is None or a['floor_id'] == fid) and (sid is None or a['space_id'] == sid)]
    per_floor = Counter(a['floor_id'] for a in items)
    per_room = Counter(a['space_id'] for a in items)
    return {'count': len(items), 'item_types': kinds, 'scope': 'inclusive chair family' if len(kinds)>1 else 'exact item type',
            'ids': [a['id'] for a in items],
            'per_floor': [{'id': f['id'], 'label': f['name'], 'count': per_floor[f['id']]} for f in sorted(building.floors.values(), key=lambda f: f['level']) if fid is None or f['id']==fid],
            'per_room': [{'id': sid, 'label': building.label(sid), 'count': n} for sid, n in sorted(per_room.items(), key=lambda p: (-p[1], p[0]))]}


def rank_by_items(building, item_type, floor=None, room_type=None):
    counted = count_items(building, item_type, floor)
    counts = {row['id']: row['count'] for row in counted['per_room']}
    ranked = sorted(({'id': s['id'], 'label': building.label(s['id']), 'floor_id': s['floor_id'], 'count': counts.get(s['id'], 0)}
                     for s in rooms(building, floor, room_type)), key=lambda r: (-r['count'], r['id']))
    return {'rows': ranked, 'total_items': sum(r['count'] for r in ranked), 'total_rooms': len(ranked),
            'item_types': counted['item_types'], 'scope': counted['scope'],
            'top_ties': sum(r['count']==ranked[0]['count'] for r in ranked) if ranked else 0}


def filter_rooms(building, requirements, floor=None, room_type=None):
    """AND semantics, with a separately validated minimum for every item descriptor."""
    counts = defaultdict(Counter)
    for a in building.assets.values():
        counts[a['space_id']][a['type']] += 1
    resolved = []
    for requirement in requirements:
        minimum = requirement.get('minimum', 1)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            raise ValueError('Item minimum must be a nonnegative integer.')
        resolved.append((asset_kinds(building, requirement['item_type']), minimum))
    matches = [s for s in rooms(building, floor, room_type)
               if all(sum(counts[s['id']][kind] for kind in kinds) >= minimum for kinds, minimum in resolved)]
    return {'rows': [{'id': s['id'], 'label': building.label(s['id']), 'floor_id': s['floor_id'], 'contents': dict(counts[s['id']])} for s in matches],
            'count': len(matches), 'requirements': [{'item_types': kinds, 'minimum': n} for kinds, n in resolved]}


def statistics(building, floor=None, room_type=None, group_by='floor'):
    if group_by not in ('floor', 'room_type'):
        raise ValueError('group_by must be floor or room_type')
    groups = defaultdict(list)
    selected = rooms(building, floor, room_type)
    for s in selected:
        groups[s['floor_id'] if group_by=='floor' else s['room_type']].append(s)
    rows = [{'id': key, 'label': building.floor_name(key) if group_by=='floor' else key.replace('_', ' '),
             'count': len(spaces), 'area_m2': round(sum(building.area(s['id']) for s in spaces), 2)}
            for key, spaces in sorted(groups.items())]
    return {'rows': rows, 'ids': [s['id'] for s in selected], 'count': len(selected),
            'total_area_m2': round(sum(building.area(s['id']) for s in selected), 2), 'group_by': group_by}


def shared_wall_lines(building, sid):
    from floorwise.core.geometry import wall_neighbours
    lines=[]
    for neighbour, _ in wall_neighbours(building, sid):
        if building.spaces[neighbour]['type'] not in ('room','hall'):
            continue
        boundary=building.polygons[sid].boundary.intersection(building.polygons[neighbour].boundary.buffer(.35,cap_style=2,join_style=2))
        parts=list(boundary.geoms) if hasattr(boundary,'geoms') else [boundary]
        for part in parts:
            if part.geom_type!='LineString' or part.length<.01:
                continue
            coords=list(part.coords)
            z=building.elevation(building.spaces[sid]['floor_id'])
            lines.extend({'a':[a[0],a[1],z],'b':[b[0],b[1],z]} for a,b in zip(coords,coords[1:]))
    return lines

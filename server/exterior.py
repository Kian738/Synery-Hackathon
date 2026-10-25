"""Read-only geographic context from a supplied OSM source reference, never guessed."""
import json
import re
from functools import lru_cache
from urllib.request import Request, urlopen


@lru_cache(maxsize=64)
def osm_way(way_id):
    request=Request(f'https://www.openstreetmap.org/api/0.6/way/{way_id}/full.json',
                    headers={'User-Agent':'Floorwise/1.0 (https://github.com/Kian738/Synery-Hackathon)','Accept':'application/json'})
    with urlopen(request,timeout=15) as response:
        raw=response.read(4_000_001)
    if len(raw)>4_000_000:raise ValueError('Mapped building response is too large')
    return describe(json.loads(raw),way_id)


def describe(data,way_id):
    nodes={n['id']:[n['lon'],n['lat']] for n in data.get('elements',[]) if n.get('type')=='node'}
    way=next((w for w in data.get('elements',[]) if w.get('type')=='way' and w['id']==int(way_id)),None)
    if not way:raise ValueError('The source building is no longer present in OpenStreetMap')
    points=[nodes[n] for n in way.get('nodes',[]) if n in nodes]
    if len(points)<4 or points[0]!=points[-1]:raise ValueError('The source way has no closed building outline')
    xs,ys=zip(*points);bounds=[[min(xs),min(ys)],[max(xs),max(ys)]]
    height=None
    raw=way.get('tags',{}).get('height','')
    if re.fullmatch(r'\d+(?:\.\d+)?(?:\s*m)?',raw):
        candidate=float(raw.rstrip(' m'))
        if 0<candidate<1000:height=candidate
    return {'source':'OpenStreetMap','source_url':f'https://www.openstreetmap.org/way/{way_id}',
            'attribution':'© OpenStreetMap contributors','license_url':'https://www.openstreetmap.org/copyright',
            'bounds':bounds,'center':[(min(xs)+max(xs))/2,(min(ys)+max(ys))/2],
            'outline':{'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[points]}},
            'recorded_height_m':height,
            'alignment':'Geographic exterior and local indoor coordinates are separate. Transition is illustrative, not a surveyed entrance alignment.'}



def exterior(building):
    source=building.info.get('source_ref',{}).get('osm','')
    match=re.fullmatch(r'way(\d+)',str(source))
    if not match:raise ValueError('This dataset has no supported geographic source reference. The indoor model is available.')
    return osm_way(match[1])

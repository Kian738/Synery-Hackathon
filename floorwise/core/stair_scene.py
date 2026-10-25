"""Conservative display-only stair shafts. Never change analytical polygons or routes."""
import math
from functools import reduce
from shapely import make_valid
from shapely.geometry import Polygon,Point


def fitted_rectangle(shared,seeds):
    """Find a bounded rectangle wholly covered by the common shaft, with display clearance."""
    safe=shared.buffer(-.08,join_style=2)
    if safe.is_empty:return None
    parts=[safe] if safe.geom_type=='Polygon' else [g for g in safe.geoms if g.geom_type=='Polygon']
    best=None;best_area=0
    for part in parts:
        if part.area<1.5:continue
        x0,y0,x1,y1=part.bounds
        centres=[part.representative_point(),part.centroid]
        centres += [Point(x0+(x1-x0)*i/4,y0+(y1-y0)*j/4) for i in range(1,4) for j in range(1,4)]
        rectangles=[part.minimum_rotated_rectangle]+[s.minimum_rotated_rectangle for s in seeds]
        axes=set()
        for rect in rectangles:
            pts=list(rect.exterior.coords)[:4]
            if len(pts)!=4:continue
            a,b,c=pts[:3];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);width=math.dist(b,c)
            if min(length,width)<1.1:continue
            ux,uy=dx/length,dy/length
            if length<width:ux,uy,length,width=-uy,ux,width,length
            if ux<0:ux,uy=-ux,-uy
            key=(round(ux,2),round(uy,2),round(length/width,2))
            if key in axes:continue
            axes.add(key)
            for centre in centres:
                if not part.covers(centre):continue
                def candidate(k):
                    return Polygon([(centre.x+u*length*k*ux/2-v*width*k*uy/2,centre.y+u*length*k*uy/2+v*width*k*ux/2) for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]])
                lo,hi=0.,1.
                for _ in range(18):
                    mid=(lo+hi)/2
                    if part.covers(candidate(mid)):lo=mid
                    else:hi=mid
                if width*lo<1.1 or length*lo<1.4:continue
                fitted=candidate(lo*.999)
                if fitted.area>best_area:
                    best=fitted;best_area=fitted.area
    return [list(p) for p in list(best.exterior.coords)[:4]] if best is not None else None


def compile_stair_shafts(data):
    spaces={s['id']:s for s in data['spaces']};floors={f['id']:f for f in data['floors']};out=[]
    for connector in data['vertical_connectors']:
        if connector['kind']!='stairs':continue
        stops=sorted([(floors[f],spaces[s]) for f,s in zip(connector['floor_ids'],connector['space_ids']) if f in floors and s in spaces],key=lambda p:p[0]['level'])
        if len(stops)<2:continue
        polygons=[make_valid(Polygon(s['polygon'])) for _,s in stops]
        common=reduce(lambda a,b:a.intersection(b),polygons)
        shared=fitted_rectangle(common,polygons)
        for i in range(len(stops)-1):
            footprint=shared or fitted_rectangle(polygons[i].intersection(polygons[i+1]),polygons[i:i+2])
            out.append({'connector_id':connector['id'],'from_floor':stops[i][0]['id'],'to_floor':stops[i+1][0]['id'],
                        'footprint':footprint,'basis':'common_all_stops' if shared else 'common_floor_pair',
                        'warning':None if footprint else 'No safe common shaft footprint; illustrative flight withheld.'})
    return out

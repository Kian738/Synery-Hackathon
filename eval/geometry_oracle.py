"""Independent shoelace/centroid oracle across source polygons; no production geometry calls for expectations."""
import argparse
import math
from eval.ledger import Ledger
from floorwise.paths import DATA
from floorwise.core.model import Building
from floorwise.core import geometry


def moments(points):
    ring=[*points,points[0]];twice=0.;mx=0.;my=0.
    for a,b in zip(ring,ring[1:]):
        cross=a[0]*b[1]-b[0]*a[1];twice+=cross;mx+=(a[0]+b[0])*cross;my+=(a[1]+b[1])*cross
    if abs(twice)<1e-10:return abs(twice)/2,None
    return abs(twice)/2,(mx/(3*twice),my/(3*twice))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--split',default='train,dev,test');args=parser.parse_args()
    ledger=Ledger('geometry_oracle',{'splits':args.split,'oracle':'independent shoelace and first moments'})
    for split in args.split.split(','):
        if split not in ('train','dev','test'):raise SystemExit('Unknown split')
        for path in sorted((DATA/split).glob('*/building.json')):
            b=Building.load(path.parent);errors=[];degenerate=[]
            for sid,space in b.spaces.items():
                expected,centre=moments(space['polygon'])
                actual=geometry.area(b,sid)
                if not math.isclose(expected,actual,rel_tol=1e-7,abs_tol=1e-6):errors.append({'space':sid,'measure':'area','expected':expected,'actual':actual})
                if centre is None:degenerate.append(sid);continue
                point=geometry.centroid_3d(b,sid)
                if not all(math.isclose(x,y,rel_tol=1e-6,abs_tol=1e-5) for x,y in zip(centre,point[:2])):
                    errors.append({'space':sid,'measure':'centroid','expected':centre,'actual':point})
            ledger.record(id=b.id,building=b.id,kind='areas and centroids',source=b.info.get('source'),correct=not errors,
                          spaces=len(b.spaces),errors=errors,degenerate=degenerate)
    result=ledger.finish()
    if result['correct']!=result['total']:raise SystemExit(1)


if __name__=='__main__':main()

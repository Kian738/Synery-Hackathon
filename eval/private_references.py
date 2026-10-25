"""Twenty hand-computable reference scenarios across walking, vertical travel,
no-outside-hop and concave geometry. Expectations are elementary arithmetic.
"""
import copy
from eval.private_corpus import reference_scenarios


def cases():
    result=[]
    for i,base in enumerate(reference_scenarios()[:5]):
        result.append({'id':f'walk-{i}','kind':'route','data':base['data'],'inputs':{'start':'A','destination':'B'},'expected':base['expected_route_m']})
    for i in range(5):
        data=copy.deepcopy(reference_scenarios()[0]['data']);rise=3.+i*.25;lift=i%2==0
        data['floors']=[{'id':f'F{j}','name':f'Floor {j}','level':j,'elevation_m':j*rise,'height_m':rise} for j in range(3)]
        data['spaces']=[{**data['spaces'][0],'id':f'C{j}','floor_id':f'F{j}','name':f'Core {j}','type':'lift' if lift else 'stair'} for j in range(3)]
        data['openings']=[];data['vertical_connectors']=[{'id':'V','kind':'lift' if lift else 'stairs','name':'Core','floor_ids':[f'F{j}' for j in range(3)],'space_ids':[f'C{j}' for j in range(3)],'step_free':lift}]
        result.append({'id':f'vertical-{i}','kind':'route','data':data,'inputs':{'start':'C0','destination':'C2'},'expected':15+2*rise if lift else 4*rise})
    for i in range(1):
        data=copy.deepcopy(reference_scenarios()[i]['data']);data['openings']=[{'id':'E1','floor_id':'F0','space_ids':['A','outside'],'kind':'entrance','position':[0,1],'width_m':1.,'step_free':True},
            {'id':'E2','floor_id':'F0','space_ids':['B','outside'],'kind':'entrance','position':[2,1],'width_m':1.,'step_free':True}]
        result.append({'id':f'no-outside-hop-{i}','kind':'route','data':data,'inputs':{'start':'A','destination':'B'},'expected':None})
    for mode in ('forklift-wide','forklift-narrow','bay-transit','bay-destination'):
        data=copy.deepcopy(reference_scenarios()[2]['data'])
        # Three 4 x 4 spaces in a straight line; centre-to-centre costs are 4 m per leg.
        data['spaces']=[{**data['spaces'][0],'id':name,'name':name,'ref':name,'polygon':[[x,0],[x+4,0],[x+4,4],[x,4]],
                         'type':'hall' if name=='B' and mode.startswith('bay') else 'corridor' if name=='B' else 'room',
                         'room_type':'production_zone' if name=='B' and mode.startswith('bay') else 'office'} for name,x in [('A',0),('B',4),('C',8)]]
        width=2.99 if mode=='forklift-narrow' else 3.
        data['openings']=[{'id':'D1','floor_id':'F0','space_ids':['A','B'],'kind':'door','position':[4,2],'width_m':width,'step_free':True},
                          {'id':'D2','floor_id':'F0','space_ids':['B','C'],'kind':'door','position':[8,2],'width_m':width,'step_free':True}]
        destination='B' if mode=='bay-destination' else 'C'
        inputs={'start':'A','destination':destination, 'forklift':mode.startswith('forklift'),'bays_are_destinations':mode.startswith('bay')}
        expected=8. if mode=='forklift-wide' else 4. if mode=='bay-destination' else None
        result.append({'id':mode,'kind':'route','data':data,'inputs':inputs,'expected':expected})
    for i in range(5):
        w,h,arm=5.+i,7.+i,1.
        data=copy.deepcopy(reference_scenarios()[0]['data'])
        data['spaces']=data['spaces'][:1];data['openings']=[]
        data['spaces'][0]['polygon']=[[0,0],[w,0],[w,arm],[arm,arm],[arm,h],[0,h]]
        area=w*arm+(h-arm)*arm
        cx=(w*arm*w/2+(h-arm)*arm*arm/2)/area
        cy=(w*arm*arm/2+(h-arm)*arm*(h+arm)/2)/area
        result.append({'id':f'concave-{i}','kind':'moments','data':data,'expected':[area,cx,cy]})
    return result


def evaluate():
    from floorwise.core.model import Building
    from floorwise.core.geometry import centroid_3d,area
    from floorwise.agent.solve import solve
    from eval.private_oracle import route,moments,graph
    for case in cases():
        b=Building(case['data'])
        if case['kind']=='route':
            got,_=solve(b,'route',case['inputs']);expected=case['expected']
            stops=[case['inputs']['start'],case['inputs']['destination']]
            prepared=graph(case['data'],forklift=case['inputs'].get('forklift',False),bays=case['inputs'].get('bays_are_destinations',False),stops=stops)
            oracle=route(case['data'],stops,prepared=prepared)
            good=(not got['reachable'] and not oracle['reachable']) if expected is None else got['reachable'] and oracle['reachable'] and abs(got['length_m']-expected)<.01 and abs(oracle['length_m']-expected)<.01
        else:
            expected=case['expected'];a,point=moments(case['data']['spaces'][0]['polygon']);actual=[area(b,'A'),*centroid_3d(b,'A')[:2]]
            good=all(abs(x-y)<1e-8 for x,y in zip(actual,expected)) and all(abs(x-y)<1e-8 for x,y in zip([a,*point],expected))
        yield case['id'],bool(good)

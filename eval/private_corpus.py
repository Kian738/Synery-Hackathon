"""New parametric buildings and separately rendered plans, never copied from kit buildings."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import random
import secrets
from collections import Counter
from pathlib import Path

from PIL import Image,ImageDraw,ImageFilter
from eval.private_oracle import moments,graph,route,numeric

VERSION=1
FAMILIES={
 'development':['spine','courtyard_links','offset_wings','dual_core','split_block','concave_branch'],
 'validation':['staggered_branches','alternating_necks'],
 'holdout':['comb_links','detached_annex']}
STYLES={'development':['flat','padded','small_text'], 'validation':['thin_walls','rescaled'], 'holdout':['compressed','dense_labels']}
PROFILES={'smoke':20,'initial':200,'expanded':2000,'industrial':200}


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf8')


def checksums(paths,root):
    from concurrent.futures import ThreadPoolExecutor
    def one(path):return path.relative_to(root).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest()
    with ThreadPoolExecutor(max_workers=8) as pool:return dict(pool.map(one,paths))


def rect(x,y,w,h):return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]


def make_building(index,family,seed,industrial=False):
    rng=random.Random(seed);bid=f'private-{index:05d}-{seed & 0xffff:04x}'
    base=-1 if index%4==0 else 0;levels=list(range(base,base+1+index%3))
    widths=[rng.randint(4,8) for _ in range(6+index%3)]
    height=rng.randint(4,7);corridor=3.2;total=sum(widths)
    data={'building':{'id':bid,'name':'Independent '+bid,'units':'m','source':'private_generated','split':'private'},'floors':[],'spaces':[],'openings':[],'vertical_connectors':[],'assets':[]}
    cores={};rise=round(rng.uniform(2.8,4.5),2)
    def door(a,b,x,y,fid,width=.9):
        oid=f'{bid}-O{len(data["openings"]):04d}'
        data['openings'].append({'id':oid,'floor_id':fid,'space_ids':[a,b],'kind':'entrance' if b=='outside' else 'door','position':[x,y],'width_m':width,'step_free':len(data['openings'])%11!=0,'synthetic':False})
    for level in levels:
        fid=f'{bid}-F{level}';fname='Ground floor' if level==0 else f'Floor {level}' if level>0 else f'Basement {-level}'
        data['floors'].append({'id':fid,'level':level,'name':fname,'elevation_m':round(level*rise,2),'height_m':rise})
        corridor_id=f'{fid}-C'
        data['spaces'].append({'id':corridor_id,'floor_id':fid,'type':'corridor','room_type':'corridor','name':f'Concourse {level}','ref':f'C{level}','polygon':rect(0,0,total,corridor),'synthetic':False})
        x=0;previous=None
        for j,w in enumerate(widths):
            kind='stair' if j==0 else 'lift' if j==len(widths)-1 or (family=='dual_core' and j==1) else 'room'
            if industrial and kind=='room' and j==3:kind='hall'
            room_height=height+(j%2 if family in ('offset_wings','staggered_branches') else 0)
            lower=family=='staggered_branches' and kind=='room' and j%2==1
            poly=rect(x,-room_height if lower else corridor,w,room_height)
            if family in ('concave_branch','comb_links') and kind=='room' and j%2:
                poly=[[x,corridor],[x+w,corridor],[x+w,corridor+room_height/2],[x+w*.65,corridor+room_height/2],[x+w*.65,corridor+room_height],[x,corridor+room_height]]
            sid=f'{fid}-S{j:02d}';ref=f'{level}.{j:02d}'
            name='Workshop' if j in (2,3) else f'{"Stairwell" if kind=="stair" else "Lift core" if kind=="lift" else "Office"} {ref}'
            data['spaces'].append({'id':sid,'floor_id':fid,'type':kind,'room_type':'stairwell' if kind=='stair' else 'lift' if kind=='lift' else 'production_zone' if kind=='hall' else 'office','name':name,'ref':ref,'polygon':poly,'synthetic':False})
            opening_width=rng.choice([.6,.89,.9,.91,1.1,1.2,2.,3.,3.2])
            if not(family in ('split_block','detached_annex') and j==len(widths)-2):
                door(corridor_id,sid,x+w/2,0 if lower else corridor,fid,opening_width)
            if family in ('courtyard_links','comb_links','alternating_necks') and previous and j>1 and (family!='alternating_necks' or j%2==0):
                door(previous,sid,x,corridor+min(height,room_height)*.45,fid,rng.choice([.89,1.2,3.]))
            if kind in ('stair','lift'):cores.setdefault((kind,j),[]).append((fid,sid))
            if kind=='room':
                _,point=moments(poly)
                for k in range(rng.randrange(0,5)):
                    data['assets'].append({'id':f'{bid}-A{len(data["assets"]):05d}','floor_id':fid,'space_id':sid,'category':'furniture','type':['chair','chair','chair','coat_rack','projector','desk'][(j+k)%6],'name':f'Equipment {len(data["assets"])+1}','position':list(point),'size':[.4,.4]})
            previous=sid;x+=w
        if level==min(levels):door(corridor_id,'outside',0,corridor/2,fid,1.2)
        if family=='detached_annex':
            sid=f'{fid}-annex';data['spaces'].append({'id':sid,'floor_id':fid,'type':'room','room_type':'office','name':f'Annex {level}','ref':f'{level}.90','polygon':rect(total+4,0,5,5),'synthetic':False})
            if level==min(levels):door(sid,'outside',total+4,2.5,fid,1.2)
    for (kind,j),stops in cores.items():
        if len(stops)<2:continue
        data['vertical_connectors'].append({'id':f'{bid}-V{j:02d}','name':f'{"Lift" if kind=="lift" else "Stairs"} {j}','kind':'lift' if kind=='lift' else 'stairs','space_ids':[s for f,s in stops],'floor_ids':[f for f,s in stops],'step_free':kind=='lift'})
    return data


def label(data,sid):
    s=next(s for s in data['spaces'] if s['id']==sid);f=next(f for f in data['floors'] if f['id']==s['floor_id'])
    count=sum(t['name']==s['name'] and t['floor_id']==s['floor_id'] for t in data['spaces'])
    return (s['ref'] if count>1 else s['name'])+' ('+f['name']+')'


def _questions(data,seed,language):
    rng=random.Random(seed);rooms=[s for s in data['spaces'] if s['type'] in ('room','hall')];out=[]
    base=data['floors'][0];prepared={}
    def oracle(stops,step_free=False,closed=(),forklift=False,bays=False):
        key=(step_free,tuple(sorted(closed)),forklift,bays,tuple(stops) if forklift or bays else ())
        if key not in prepared:prepared[key]=graph(data,step_free,closed,forklift=forklift,bays=bays,stops=stops)
        return route(data,stops,step_free,closed,prepared=prepared[key])
    for i in range(50):
        a,b,c=rng.sample(rooms,3);closed=[];sf=False
        row={'id':f'{data["building"]["id"]}-Q{i:02d}','language_family':language}
        if i<24:
            sf=12<=i<18;closed=[rng.choice(data['vertical_connectors'])['id']] if 18<=i<22 and data['vertical_connectors'] else []
            kind='tour' if i>=22 else 'route';stops=[a['id'],c['id'],b['id']] if kind=='tour' else [a['id'],b['id']]
            inputs={'stops':stops} if kind=='tour' else {'start':stops[0],'destination':stops[-1]}
            inputs['step_free']=sf
            if closed:inputs['closed']=closed[0]
            source=label(data,stops[0]);target=label(data,stops[-1])
            text=(f'Starting at {source}, visit {label(data,stops[1])}, then {target} in this order. What is the route?' if kind=='tour' else f'{"Is there a step-free route" if sf else "How do I get"} from {source} to {target}?')
            if closed:
                cn=next(v['name'] for v in data['vertical_connectors'] if v['id']==closed[0]);text=f'{cn} is closed for maintenance. '+text
            if language=='direct_request' and kind=='route' and not closed:text=f'Please find {"a step-free" if sf else "an indoor"} route from {source} to {target}.'
            if language=='spoken_correction' and kind=='route' and not closed:text=f'I need to reach {target}, starting from {source}. '+('No stairs, please.' if sf else '')
            industrial=any(s['room_type']=='production_zone' for s in data['spaces'])
            forklift=industrial and i==10;bays=industrial and i==11
            if forklift:inputs['forklift']=True;text+=' A forklift is driving; use openings at least 3 m wide.'
            if bays:inputs['bays_are_destinations']=True;text+=' Production bays are destinations, never shortcuts.'
            row.update(kind=kind,layer='solver_and_text',inputs=inputs,text=text,expected=oracle(stops,sf,closed,forklift,bays),stops=stops)
        elif i<28:
            f=data['floors'][(i-24)%len(data['floors'])];kind='count';item=['chair','coat_rack','projector','desk'][i-24];inputs={'asset_type':item,'floor_id':f['id']}
            row.update(kind=kind,layer='solver_and_text',inputs=inputs,text=f'How many {item.replace("_"," ")} items are on the {f["name"]}?' ,expected=numeric(data,kind,inputs))
        elif i<32:
            f=data['floors'][(i-28)%len(data['floors'])];kind='floor_area_total';room_type=['office','corridor','lift','stairwell'][i-28];inputs={'room_type':room_type,'floor_id':f['id']}
            row.update(kind=kind,layer='solver_and_text',inputs=inputs,text=f'What is the total floor area of all {room_type} spaces on the {f["name"]}?' ,expected=numeric(data,kind,inputs))
        elif i<36:
            kind='straight_line_3d';inputs={'first':a['id'],'second':b['id']}
            row.update(kind=kind,layer='solver_and_text',inputs=inputs,text=f'Between {label(data,a["id"])} and {label(data,b["id"])}. What is the straight-line distance?',expected=numeric(data,kind,inputs))
        elif i<40:
            kind='wide_delivery_count';width=[.89,.9,1.2,3.][i-36];inputs={'start':a['id'],'floor_id':a['floor_id'],'min_width':width}
            f=next(f for f in data['floors'] if f['id']==a['floor_id'])
            row.update(kind=kind,layer='solver_and_text',inputs=inputs,text=f'A {width} m wide trolley arrives through the entrance into {label(data,a["id"])}. Into how many rooms on the {f["name"]} can it get?',expected=numeric(data,kind,inputs))
        elif i<44:
            f=data['floors'][(i-40)%len(data['floors'])];ids=[s['id'] for s in rooms if s['floor_id']==f['id'] and s['name']=='Workshop']
            mode=i-40
            mention='Workshop ('+f['name']+')' if mode==0 else 'Workshop' if mode==1 else label(data,ids[0]) if mode==2 else 'Nonexistent place ZXQ-999999'
            expected=ids if mode==0 else [s['id'] for s in rooms if s['name']=='Workshop'] if mode==1 else [ids[0]] if mode==2 else []
            row.update(kind='ambiguity',layer='resolver_contract',text=mention,expected=expected)
        else:
            # Explicit API-level conversation contracts; these are not claimed as live language tests.
            width=[None,.9,1.2][i%3];sf=True
            closed=[data['vertical_connectors'][-1]['id']] if data['vertical_connectors'] and i%2 else []
            destination=c if i%2 else b
            row.update(kind='context_correction',layer='session_contract',text=[f'I am at {label(data,a["id"])}. I need step-free access.',f'Change the destination to {label(data,destination["id"])}; keep my start and requirements.'],
                       inputs={'start':a['id'],'destination':destination['id'],'first_destination':b['id'],'step_free':True,'min_width':width,'closed':closed},
                       expected=route(data,[a['id'],destination['id']],True,closed,width or 0.))
        out.append(row)
    return out


def questions(data,seed,language):
    """Fifty distinct requests per building; retries never depend on solver outputs."""
    rows=[];seen=set()
    for attempt in range(20):
        for row in _questions(data,seed+attempt*7919,language):
            key=json.dumps({k:v for k,v in row.items() if k!='id'},sort_keys=True)
            if key not in seen:
                seen.add(key);rows.append(row)
            if len(rows)==50:
                for i,item in enumerate(rows):item['id']=f'{data["building"]["id"]}-Q{i:02d}'
                return rows
    raise ValueError('Cannot produce 50 distinct requests for this source building')


def render(data,path,style,seed,floor_index=0):
    rng=random.Random(seed);level=data['floors'][floor_index]['level'];fid=data['floors'][floor_index]['id']
    spaces=[s for s in data['spaces'] if s['floor_id']==fid]
    points=[p for s in spaces for p in s['polygon']];x0=min(p[0] for p in points);x1=max(p[0] for p in points);y0=min(p[1] for p in points);y1=max(p[1] for p in points)
    scale=6 if style=='rescaled' else 9;pad=35 if style=='padded' else 12
    image=Image.new('RGB',(round((x1-x0)*scale)+2*pad+1,round((y1-y0)*scale)+2*pad+1),'white');draw=ImageDraw.Draw(image)
    def px(p):return (round((p[0]-x0)*scale)+pad,round((y1-p[1])*scale)+pad)
    fills={'room':(227,237,247),'corridor':(220,220,220),'stair':(238,215,162),'lift':(187,213,237),'hall':(241,220,188)}
    for s in spaces:
        fill=fills[s['type']]
        if style=='dense_labels':fill=tuple(min(249,max(150,v+rng.randint(-5,5))) for v in fill)
        draw.polygon([px(p) for p in s['polygon']],fill=fill,outline=(35,35,35),width=1 if style=='thin_walls' else 2)
        _,center=moments(s['polygon']);cx,cy=px(center)
        if style in ('small_text','dense_labels'):draw.text((cx-8,cy-3),s['ref'],fill=(50,50,50))
    for o in data['openings']:
        if o['floor_id']!=fid:continue
        x,y=px(o['position']);radius=2 if style=='rescaled' else 3
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(230,50,50) if 'outside' in o['space_ids'] else (139,69,19))
    if style=='compressed':
        import io
        buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=88);buffer.seek(0);image=Image.open(buffer).convert('RGB')
    image.save(path)
    truth={'building':data['building'],'floors':[data['floors'][floor_index]],'spaces':spaces,'openings':[o for o in data['openings'] if o['floor_id']==fid],'vertical_connectors':[],'assets':[]}
    return truth,x1-x0


def reference_scenarios():
    refs=[]
    for i in range(20):
        w=2+i%5;h=4+i//5
        a={'id':'A','floor_id':'F0','name':'A','ref':'A','type':'room','room_type':'office','polygon':rect(0,0,w,h)}
        b={**a,'id':'B','name':'B','ref':'B','polygon':rect(w,0,w,h)}
        data={'building':{'id':f'reference-{i:02d}','source':'analytic_reference','units':'m'},'floors':[{'id':'F0','name':'Ground floor','level':0,'elevation_m':0,'height_m':3.}],
              'spaces':[a,b],'assets':[],'vertical_connectors':[],'openings':[{'id':'D','floor_id':'F0','space_ids':['A','B'],'kind':'door','position':[w,h/2],'width_m':.9,'step_free':True}]}
        refs.append({'id':data['building']['id'],'data':data,'expected_area':w*h,'expected_centroid':[w/2,h/2],
                     'expected_route_m':w,'derivation':'Two equal rectangles; centre-to-centre horizontal walk through shared midpoint = rectangle width.'})
    return refs


def create(root,profile):
    root=Path(root)
    if (root/'manifest.json').exists():raise ValueError('Corpus already exists; use it unchanged or choose a fresh root/generation')
    if root.exists() and any(root.iterdir()):raise ValueError('Refusing to overwrite nonempty corpus directory')
    root.mkdir(parents=True,exist_ok=True)
    seed=secrets.randbits(64);count=PROFILES[profile];entries=[];image_cases=[];hashes={}
    family_order=[(split,f) for split,fs in FAMILIES.items() for f in fs]
    for index in range(count):
        split,family=family_order[index%len(family_order)];local_seed=seed+index*100003
        data=make_building(index,family,local_seed,industrial=profile=='industrial');bid=data['building']['id'];folder=root/'buildings'/bid;folder.mkdir(parents=True)
        language={'development':'canonical','validation':'direct_request','holdout':'spoken_correction'}[split]
        dump(folder/'building.json',data)
        qs=questions(data,local_seed,language)
        (folder/'questions.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in qs),encoding='utf8')
        entries.append({'id':bid,'path':str(folder.relative_to(root)).replace('\\','/'),'split':split,'family':family,'language':language,'questions':len(qs)})
        for variant in range(3):
            style=STYLES[split][variant%len(STYLES[split])];caseid=f'{bid}-I{variant}'
            floor_images={};width=None
            for floor_index,floor in enumerate(data['floors']):
                output=root/'images'/f'{caseid}-F{floor["level"]}.png';output.parent.mkdir(exist_ok=True)
                _,floor_width=render(data,output,style,local_seed+variant,floor_index)
                floor_images[str(floor['level'])]=output.relative_to(root).as_posix()
                if floor_index==0:width=floor_width
            dump(root/'images'/f'{caseid}.truth.json',data)
            image_cases.append({'id':caseid,'building':bid,'split':split,'family':family,'style':style,
                                'image':next(iter(floor_images.values())),'floor_images':floor_images,'truth':f'images/{caseid}.truth.json',
                                'width_m':width if variant!=2 else None,'expected_behavior':'review_required' if variant==2 else 'reconstruct',
                                'difficulty':'missing_scale' if variant==2 else 'image_variation'})
        if (index+1)%25==0:print(f'Generated {index+1}/{count} independent buildings',flush=True)
    dump(root/'references.json',reference_scenarios())
    hashes=checksums(sorted(p for p in root.rglob('*') if p.is_file()),root)
    manifest={'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('private_oracle.py').read_bytes()).hexdigest(),'version':VERSION,'profile':profile,'generation':secrets.token_hex(8),'seed':seed,'buildings':entries,'images':image_cases,
              'counts':{'buildings':count,'questions':sum(e['questions'] for e in entries),'image_cases':len(image_cases),'raster_images':sum(len(c['floor_images']) for c in image_cases),'analytic_references':20},
              'family_partition':FAMILIES,'style_partition':STYLES,'hashes':hashes,'oracle':'independent kit graph; pure arithmetic numeric expectations',
              'privacy':'Local gitignored corpus, frozen by checksums; not secret from its author.'}
    dump(root/'manifest.json',manifest)
    print(json.dumps(manifest['counts']),flush=True)
    return manifest

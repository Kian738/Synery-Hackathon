import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { advancePreview, routeRuns, presentation, samplePreview, type Presentation } from "../lib/playback";
import { openingFrame } from "../lib/openings";
import { bounds, zoneOf } from "../lib/geometry";
import type { Asset, Geometry, Opening, Route, Space, VisualResult } from "../lib/types";

const COLORS: Record<string,string> = {circulation:"#647a83", hall:"#586b70", office:"#82969b", lab:"#668e89", service:"#7b7d8c", core:"#435c66"};
const frame = (x:number,y:number,h:number) => new THREE.Vector3(x,h,-y);
function floorShape(space: Space) {
  const shape = new THREE.Shape();
  space.polygon.forEach(([x,y],i) => i ? shape.lineTo(x,y) : shape.moveTo(x,y));
  const g = new THREE.ShapeGeometry(shape);
  g.rotateX(-Math.PI/2);
  return g;
}

function Floors({spaces,elevation,highlights,onPick}:{spaces:Space[];elevation:number;highlights:Set<string>;onPick?:(s:Space)=>void}) {
  const batches = useMemo(() => {
    const groups = new Map<string,Space[]>();
    spaces.forEach(s => {const key=highlights.has(s.id)?"highlight":zoneOf(s); groups.set(key,[...(groups.get(key)??[]),s]);});
    return [...groups].map(([zone,rooms]) => {
      let triangles=0;
      const ranges:{end:number;space:Space}[]=[];
      const pieces=rooms.map(s=>{const g=floorShape(s).toNonIndexed();triangles+=g.getAttribute("position").count/3;ranges.push({end:triangles,space:s});return g;});
      const geometry=mergeGeometries(pieces); pieces.forEach(p=>p.dispose());
      return {zone,geometry,ranges};
    });
  },[spaces,highlights]);
  useEffect(()=>()=>batches.forEach(b=>b.geometry?.dispose()),[batches]);
  return <group position={[0,elevation,0]}>{batches.map((b,index)=>b.geometry&&<mesh key={b.zone} geometry={b.geometry}
    onAfterRender={renderer=>{renderer.domElement.dataset.scenePainted="true";}}
    onClick={(e:ThreeEvent<MouseEvent>)=>{e.stopPropagation();const room=b.ranges.find(r=>(e.faceIndex??0)<r.end);if(room)onPick?.(room.space);}}>
    <meshStandardMaterial color={b.zone==="highlight"?"#ffd45c":COLORS[b.zone]??COLORS.office} roughness={0.94} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-index-1}/>
  </mesh>)}</group>;
}

function Walls({geometry,floorId,elevation,follow}:{geometry:Geometry;floorId:string;elevation:number;follow:boolean}) {
  const mesh=useMemo(()=>{
    const pos:number[]=[];
    const walls=geometry.scene?.walls.filter(w=>w.floor_id===floorId)??[];
    for(const w of walls){
      const [x,z]=[w.a[0],-w.a[1]], [u,v]=[w.b[0],-w.b[1]];
      // Cutaway heights in overview; supplied heights in the eye-level view.
      const h=follow?w.height_m:Math.min(w.height_m,1.35);
      pos.push(x,0,z,u,0,v,u,h,v,x,0,z,u,h,v,x,h,z);
    }
    const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.Float32BufferAttribute(pos,3));g.computeVertexNormals();return g;
  },[geometry.scene?.revision,floorId,follow]);
  const edges=useMemo(()=>new THREE.EdgesGeometry(mesh,30),[mesh]);
  useEffect(()=>()=>{mesh.dispose();edges.dispose();},[mesh,edges]);
  return <group position={[0,elevation,0]}><mesh geometry={mesh}><meshStandardMaterial color="#b5c5c6" roughness={0.85} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}/></mesh>
    <lineSegments geometry={edges}><lineBasicMaterial color="#f0f8fa" transparent opacity={0.18}/></lineSegments></group>;
}

function Doorways({geometry,floorId,elevation,follow}:{geometry:Geometry;floorId:string;elevation:number;follow:boolean}) {
  const ref=useRef<THREE.InstancedMesh>(null);
  const parts=useMemo(()=>geometry.openings.filter(o=>o.floor_id===floorId&&Number.isFinite(o.width_m)&&o.width_m>0&&["door","entrance","opening"].includes(o.kind)).flatMap(o=>{
    const alignment=openingFrame(geometry,o);if(!alignment)return [];
    const height=follow?Math.min(2.1,(geometry.floors.find(f=>f.id===floorId)?.height_m??3)-.1):1.25;
    const width=Math.max(.1,o.width_m),color=o.kind==="entrance"?"#66bea0":o.kind==="opening"?"#8cabb7":"#bba786";
    const base={alignment,color};
    const parts=[{...base,x:0,y:.012,w:width,h:.025,d:.22}];
    if(o.kind!=="opening")parts.push(...[-1,1].map(sign=>({...base,x:sign*(width/2+.025),y:height/2,w:.055,h:height,d:.12})),{...base,x:0,y:height,w:width+.1,h:.07,d:.12});
    return parts;
  }),[geometry,floorId,follow]);
  useEffect(()=>{if(!ref.current)return;const parent=new THREE.Object3D(),part=new THREE.Object3D();parts.forEach((p,i)=>{
    parent.position.set(p.alignment.x,0,-p.alignment.y);parent.rotation.y=p.alignment.angle;parent.updateMatrix();
    part.position.set(p.x,p.y,0);part.scale.set(p.w,p.h,p.d);part.updateMatrix();
    ref.current!.setMatrixAt(i,parent.matrix.clone().multiply(part.matrix));ref.current!.setColorAt(i,new THREE.Color(p.color));
  });ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;ref.current.computeBoundingSphere();},[parts]);
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}><boxGeometry/><meshStandardMaterial roughness={.7} metalness={.15}/></instancedMesh></group>;
}

function Ceiling({spaces,elevation}:{spaces:Space[];elevation:number}) {
  const geometry=useMemo(()=>{const parts=spaces.map(floorShape),merged=parts.length?mergeGeometries(parts):null;parts.forEach(g=>g.dispose());return merged;},[spaces]);
  useEffect(()=>()=>geometry?.dispose(),[geometry]);
  return geometry?<mesh geometry={geometry} position={[0,elevation-.025,0]}><meshStandardMaterial color="#c1c8c6" roughness={1} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1}/></mesh>:null;
}

function assetStyle(a:Asset){
  if(/coffee|printer|fridge|cabinet|locker|shelf|rack/.test(a.type))return {height:1.5,color:"#344c58"};
  if(/table|desk|bench|counter/.test(a.type))return {height:0.76,color:"#b39a74"};
  if(/chair|sofa|bed/.test(a.type))return {height:0.65,color:"#536b7c"};
  if(a.category==="machine")return {height:1.65,color:"#577e87"};
  return {height:0.85,color:"#9badad"};
}
function FurnitureBatch({assets,elevation,highlighted,muted=false}:{assets:Asset[];elevation:number;highlighted:boolean;muted?:boolean}){
  const ref=useRef<THREE.InstancedMesh>(null);
  const parts=useMemo(()=>assets.flatMap(a=>{
    const look=assetStyle(a);
    const base={asset:a,color:look.color};
    const box=(x:number,y:number,z:number,w:number,h:number,d:number,color=look.color)=>({...base,x,y,z,w,h,d,color});
    if(a.type==="internal_stairs"&&a.footprint&&a.footprint.depth_m>=1.6&&a.footprint.width_m>=.8)return Array.from({length:8},(_,i)=>box(0,(i+1)*.075,-.5+(i+.5)/8,1,(i+1)*.15,1/8,"#9eabae"));
    if(/table|desk|bench|counter/.test(a.type))return [box(0,.75,0,1,.08,1),...[-.4,.4].flatMap(x=>[-.4,.4].map(z=>box(x,.35,z,.08,.7,.08,"#49565d")))];
    if(/lecture_seating_row/.test(a.type))return [box(0,.43,0,1,.1,.7),box(0,.72,-.38,1,.5,.1),box(-.4,.2,0,.1,.4,.7),box(.4,.2,0,.1,.4,.7)];
    if(/chair|seat|stool/.test(a.type))return [box(0,.43,0,.9,.1,.85),box(0,.72,-.4,.9,.5,.1),box(0,.2,0,.3,.4,.3,"#3c4b54")];
    if(/coffee/.test(a.type))return [box(0,.5,0,1,1,1),box(0,1.2,-.1,.9,.5,.7,"#233841"),box(0,.95,.38,.6,.1,.2,"#d1dce0")];
    if(/oscilloscope/.test(a.type))return [box(0,.7,0,1,.08,1,"#ab9c80"),box(0,.9,0,.65,.35,.5,"#d1d7cf"),box(-.12,.92,.26,.35,.2,.02,"#2c695e"),box(.23,.92,.26,.08,.08,.03,"#ffd45c"),...[-.4,.4].map(x=>box(x,.33,0,.08,.65,.8,"#45545b"))];
    if(/printer/.test(a.type))return [box(0,.4,0,.95,.8,.85,"#b1c1c5"),box(0,.85,0,1,.12,1,"#334b55"),box(0,.65,.44,.65,.15,.05,"#243841")];
    if(a.category==="machine")return [box(0,.15,0,1,.3,1,"#354d57"),box(0,.9,0,.85,1.2,.85),box(.3,1.55,.3,.25,.25,.25,"#ccd8d9")];
    if(/shelf|rack|bookshelf/.test(a.type))return [box(-.45,.85,0,.1,1.7,1),box(.45,.85,0,.1,1.7,1),...[.1,.65,1.2,1.7].map(y=>box(0,y,0,1,.07,1))];
    return [box(0,look.height/2,0,1,look.height,1)];
  }),[assets]);
  useEffect(()=>{if(!ref.current)return;const parent=new THREE.Object3D(),o=new THREE.Object3D();parts.forEach((p,i)=>{
    const a=p.asset,w=a.footprint?.width_m??.5,d=a.footprint?.depth_m??.5;
    parent.position.set(a.position[0],0,-a.position[1]);parent.rotation.set(0,(a.footprint?.rotation_deg??0)*Math.PI/180,0);parent.updateMatrix();
    o.position.set(p.x*w,p.y,p.z*d);o.scale.set(p.w*w,p.h,p.d*d);o.updateMatrix();
    ref.current!.setMatrixAt(i,parent.matrix.clone().multiply(o.matrix));ref.current!.setColorAt(i,new THREE.Color(highlighted?"#ffd45c":p.color).lerp(new THREE.Color("#536670"),muted ? .55 : 0));
  });ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;
  ref.current.computeBoundingSphere();},[parts,highlighted,muted]);
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}><boxGeometry/>
    <meshStandardMaterial roughness={0.8} metalness={0.1}/></instancedMesh></group>;
}

const FloorScene=memo(function FloorScene({geometry,floorId,elevation,highlights,onSpaceClick,follow,ceiling,span}:{geometry:Geometry;floorId:string;elevation:number;highlights:Set<string>;onSpaceClick?:(s:Space)=>void;follow:boolean;ceiling:boolean;span:number}) {
  const spaces=useMemo(()=>geometry.spaces.filter(s=>s.floor_id===floorId),[geometry,floorId]);
  const assets=useMemo(()=>geometry.assets.filter(a=>a.floor_id===floorId),[geometry,floorId]);
  const height=geometry.floors.find(f=>f.id===floorId)?.height_m??3;
  const roomHighlights=highlights;
  return <group>
        <Floors spaces={spaces} elevation={elevation} highlights={roomHighlights} onPick={onSpaceClick}/>
        <Walls geometry={geometry} floorId={floorId} elevation={elevation} follow={follow}/>
        <Doorways geometry={geometry} floorId={floorId} elevation={elevation} follow={follow}/>
        {follow&&ceiling&&<Ceiling spaces={spaces} elevation={elevation+height}/>}
        {geometry.connectors.flatMap(c=>c.space_ids.map(id=>({c,s:spaces.find(s=>s.id===id)}))).filter(pair=>pair.s).map(({c,s})=>{const b=bounds(s!.polygon);return <group key={s!.id} position={[(b.minX+b.maxX)/2,elevation+.08,-(b.minY+b.maxY)/2]}>
          <mesh rotation={[-Math.PI/2,0,0]}><planeGeometry args={[Math.min(1,b.maxX-b.minX),Math.min(1,b.maxY-b.minY)]}/><meshStandardMaterial color={c.kind==="lift"?"#5e92a4":"#b4a378"}/></mesh>
          {c.kind==="stairs"&&[-.3,0,.3].map(z=><mesh key={z} position={[0,.01,z]}><boxGeometry args={[.8,.015,.04]}/><meshBasicMaterial color="#e6e8e6"/></mesh>)}
          {!follow&&<Html center distanceFactor={span*.5} position={[0,.7,0]} style={{pointerEvents:"none"}}><span className="world-label">{c.kind==="lift"?"Lift":"Stairs"}</span></Html>}
        </group>;})}
        <FurnitureBatch assets={assets.filter(a=>!highlights.has(a.id))} elevation={elevation} highlighted={false} muted={highlights.size>0}/>
        <FurnitureBatch assets={assets.filter(a=>highlights.has(a.id))} elevation={elevation} highlighted/>
  </group>;
});

function Path({route,geometry,explode=0,ghost=false,xray=false,visibleFloors}:{route:Route;geometry:Geometry;explode?:number;ghost?:boolean;xray?:boolean;visibleFloors:Set<string>}){
  const runs=useMemo(()=>routeRuns(route,visibleFloors).map(run=>run.map(p=>{
    const f=geometry.floors.find(f=>f.id===p.floor_id);return frame(p.x,p.y,(f?.elevation_m??0)+(f?.level??0)*explode+.06);
  })),[route,geometry,explode,visibleFloors]);
  return <>{runs.map((r,i)=><group key={i}>
    <Line points={r} color={ghost?"#91a6b1":"#10171c"} lineWidth={ghost?3:10} depthTest={!xray} depthWrite={false} renderOrder={100} transparent opacity={ghost?0.35:1}/>
    {!ghost&&<Line points={r} color="#ffd45c" lineWidth={5} depthTest={!xray} depthWrite={false} renderOrder={101} transparent opacity={1}/>} 
  </group>)}</>;

}

const cameraMemory=new Map<string,{position:THREE.Vector3;target:THREE.Vector3}>();
function FitBuilding({box,height,activeElevation,cacheKey,fitVersion}:{box:{minX:number;maxX:number;minY:number;maxY:number};height:number;activeElevation:number;cacheKey:string;fitVersion:number}) {
  const {camera,controls,size,invalidate}=useThree();
  const previousFit=useRef(fitVersion);
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const saved=cameraMemory.get(cacheKey);
    if(saved&&previousFit.current===fitVersion){camera.position.copy(saved.position);c.target.copy(saved.target);c.update();invalidate();}
    else {
    const target=new THREE.Vector3((box.minX+box.maxX)/2,activeElevation+height/2,-(box.minY+box.maxY)/2);
    const radius=Math.hypot(box.maxX-box.minX,box.maxY-box.minY,height)/2;
    const vertical=40*Math.PI/180,horizontal=2*Math.atan(Math.tan(vertical/2)*size.width/size.height);
    const distance=radius/Math.sin(Math.min(vertical,horizontal)/2)*1.12;
    camera.position.copy(target).add(new THREE.Vector3(.65,.8,.8).normalize().multiplyScalar(distance));
    c.target.copy(target);c.update();invalidate();
    }
    previousFit.current=fitVersion;
    return ()=>{cameraMemory.set(cacheKey,{position:camera.position.clone(),target:c.target.clone()});if(cameraMemory.size>64)cameraMemory.delete(cameraMemory.keys().next().value!);};
  },[box,height,activeElevation,camera,controls,cacheKey,fitVersion,invalidate]);return null;
}

function CameraActions({action}:{action:{id:number;kind:string}}){
  const {camera,controls,invalidate}=useThree();
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const offset=camera.position.clone().sub(c.target);
    if(action.kind==="zoom-in")camera.position.copy(c.target).add(offset.multiplyScalar(.8));
    if(action.kind==="zoom-out")camera.position.copy(c.target).add(offset.multiplyScalar(1.25));
    if(action.kind==="left"||action.kind==="right"){
      const delta=new THREE.Vector3(action.kind==="left"?-3:3,0,0);camera.position.add(delta);c.target.add(delta);
    }
    if(action.kind==="up"||action.kind==="down"){
      const delta=new THREE.Vector3(0,0,action.kind==="up"?-3:3);camera.position.add(delta);c.target.add(delta);
    }
    c.update();invalidate();
  },[action,camera,controls,invalidate]);return null;
}

function RouteCamera({geometry,model,clock,playing,speed,seekVersion,onSample}:{geometry:Geometry;model:Presentation;clock:MutableRefObject<number>;playing:boolean;speed:number;seekVersion:number;onSample:(time:number)=>void}){
  const {camera,invalidate,gl}=useThree();const lastReport=useRef(-1);const first=useRef(true);const lastTick=useRef(performance.now());
  useLayoutEffect(()=>{lastTick.current=performance.now();},[playing]);
  useEffect(()=>{first.current=true;invalidate();},[seekVersion,model,invalidate]);
  useFrame((_,dt)=>{
    const now=performance.now(),elapsed=Math.max(0,(now-lastTick.current)/1000);lastTick.current=now;
    if(playing)clock.current=advancePreview(clock.current,elapsed,speed,model.duration);
    const sample=samplePreview(model,clock.current),p=sample.point;if(!p)return;
    const height=geometry.floors.find(f=>f.id===p.floor_id)?.elevation_m??0;
    camera.position.copy(frame(p.x,p.y,height+1.65));
    const ahead=samplePreview(model,Math.min(model.duration,clock.current+.75));
    const useAhead=!sample.transition&&!ahead.transition&&ahead.point?.floor_id===p.floor_id&&Math.hypot(ahead.point.x-p.x,ahead.point.y-p.y)>.01;
    const direction=useAhead?new THREE.Vector3(ahead.point!.x-p.x,0,-(ahead.point!.y-p.y)):new THREE.Vector3(sample.heading[0],0,-sample.heading[1]);
    direction.y=-direction.length()*.14;
    if(direction.lengthSq()>.00001){
      const matrix=new THREE.Matrix4().lookAt(camera.position,camera.position.clone().add(direction),new THREE.Vector3(0,1,0));
      const target=new THREE.Quaternion().setFromRotationMatrix(matrix);
      if(first.current)camera.quaternion.copy(target);else camera.quaternion.rotateTowards(target,Math.PI*dt);
      first.current=false;
    }
    camera.updateProjectionMatrix();gl.domElement.dataset.cameraPosition=JSON.stringify(camera.position.toArray());gl.domElement.dataset.cameraFloor=p.floor_id;
    if(Math.abs(clock.current-lastReport.current)>.08 || sample.arrived || !playing){lastReport.current=clock.current;onSample(clock.current);}
    if(playing)invalidate();
  });return null;
}

export function Building3D({geometry,floorId,route,previousRoute,highlights=new Set(),closed=new Set(),previewDoor,showAll,scope="current",exploded=true,follow=false,previewMode=true,activeStep=0,seekRequest=0,onStep,onSpaceClick,onFinish,onPreview,here,selected,visualResult,onPosition,heading,onRepeat}: {
 geometry:Geometry;floorId:string;route?:Route|null;previousRoute?:Route|null;highlights?:Set<string>;closed?:Set<string>;previewDoor?:Opening|null;
 onRepeat?:()=>void;heading?:number;visualResult?:VisualResult|null;onPosition?:(p:{x:number;y:number;floor_id:string})=>void;showAll:boolean;scope?:"current"|"route"|"building";exploded?:boolean;previewMode?:boolean;seekRequest?:number;onFinish?:()=>void;onPreview?:()=>void;here?:string|null;selected?:string|null;follow?:boolean;activeStep?:number;onStep?:(i:number)=>void;onSpaceClick?:(s:Space)=>void;
}){
  const reduced=typeof matchMedia!=="undefined"&&matchMedia("(prefers-reduced-motion: reduce)").matches;
  const emphasis=selected??(visualResult?.measurements.primary_ids as string[]|undefined)?.[0];
  const [action,setAction]=useState({id:0,kind:""});
  const [ceiling,setCeiling]=useState(true);
  const [fitVersion,setFitVersion]=useState(0);
  const [playing,setPlaying]=useState(false),[time,setTime]=useState(0),[speed,setSpeed]=useState(1),[seekVersion,setSeekVersion]=useState(0);
  const clock=useRef(0), model=useMemo(()=>route?presentation(route):null,[route]);
  const sample=model?samplePreview(model,time):null;
  const seek=(value:number)=>{value=Math.max(0,Math.min(value,model?.duration??0));clock.current=value;setTime(value);setSeekVersion(v=>v+1);};
  useEffect(()=>{seek(0);setPlaying(false);},[route,follow]);
  useEffect(()=>{if(!previewMode)setPlaying(false);},[previewMode]);
  useEffect(()=>{const pause=()=>setPlaying(false);window.addEventListener("floorwise:voice-start",pause);return()=>window.removeEventListener("floorwise:voice-start",pause);},[]);
  useEffect(()=>{if(model)seek(model.chapters[activeStep]??0);},[seekRequest]);
  useEffect(()=>{const hidden=()=>{if(document.hidden)setPlaying(false);};document.addEventListener("visibilitychange",hidden);return()=>document.removeEventListener("visibilitychange",hidden);},[]);
  useEffect(()=>{if(!follow||!previewMode)return;const key=(e:KeyboardEvent)=>{if(/INPUT|SELECT|TEXTAREA|BUTTON/.test((e.target as HTMLElement)?.tagName))return;if(e.code==="Space"&&!reduced){e.preventDefault();setPlaying(v=>!v);}if(e.code==="ArrowRight"||e.code==="ArrowLeft"){e.preventDefault();seek(Math.max(0,Math.min(model?.duration??0,clock.current+(e.code==="ArrowRight"?5:-5))));}};window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);},[follow,previewMode,model,reduced]);
  const report=(value:number)=>{setTime(old=>Math.abs(old-value)>.001?value:old);if(!model)return;const s=samplePreview(model,value);if(s.step!==activeStep)onStep?.(s.step);if(s.point)onPosition?.(s.point);if(s.arrived)setPlaying(false);};
  const box=useMemo(()=>bounds(geometry.spaces.flatMap(s=>s.polygon)),[geometry]);
  const fitBox=useMemo(()=>{
    const rooms=geometry.spaces.filter(s=>(scope!=="current"||visualResult?.kind==="stacking"||visualResult?.kind==="distance"||s.floor_id===floorId)&&(emphasis?s.id===emphasis:highlights.has(s.id)));
    const points=[...rooms.flatMap(s=>s.polygon),...geometry.assets.filter(a=>!emphasis&&(scope!=="current"||a.floor_id===floorId)&&highlights.has(a.id)).map(a=>a.position)];
    if(!points.length)return box;
    const b=bounds(points),pad=3;return {minX:b.minX-pad,maxX:b.maxX+pad,minY:b.minY-pad,maxY:b.maxY+pad};
  },[geometry,floorId,emphasis,highlights,box,scope,visualResult?.kind]);
  const cx=(box.minX+box.maxX)/2,cz=-(box.minY+box.maxY)/2,span=Math.max(box.maxX-box.minX,box.maxY-box.minY,10);
  const multi=((visualResult?.kind==="stacking"||visualResult?.kind==="distance")||showAll||scope==="building"||(scope==="route"&&!!route))&&!follow;
  const explode=multi&&exploded&&visualResult?.kind!=="distance"?2:0;
  const elevation=(id:string)=>{const f=geometry.floors.find(f=>f.id===id);return (f?.elevation_m??0)+(f?.level??0)*explode;};
  const activeFloor=follow?(sample?.point?.floor_id??floorId):floorId;
  const floors=geometry.floors.filter(f=>(visualResult?.kind==="stacking"||visualResult?.kind==="distance")&&!follow?visualResult.floor_ids.includes(f.id):multi?(scope==="route"?route?.floors.includes(f.id):true):f.id===activeFloor);
  const visibleFloors=useMemo(()=>new Set(floors.map(f=>f.id)),[floors.map(f=>f.id).join()]);
  const roomHighlights=useMemo(()=>new Set([...highlights,...(selected?[selected]:[])]),[highlights,selected]);
  return <div className="building-stage" data-testid="building-scene" data-scene-revision={geometry.scene?.revision} data-visible-floors={[...visibleFloors].join(",")} data-playback-state={sample?.arrived?"arrived":sample?.transition?"transition":playing?"playing":time?"paused":"idle"}>
    <Canvas frameloop={playing&&previewMode&&!reduced?"always":"demand"} dpr={[1,1.5]} camera={{position:[cx+span*.65,span*.8,cz+span*.8],fov:follow?70:40,near:.05,far:span*25}} gl={{antialias:true}}
      onCreated={({gl})=>{gl.setClearColor("#10171c");}}>
      <ambientLight intensity={follow?1.3:.65}/><hemisphereLight args={["#edf5ff","#59645c",follow?1.5:1.1]}/>
      <directionalLight position={[cx+30,80,cz+40]} intensity={1.7}/><directionalLight position={[cx-30,20,cz-25]} intensity={.6} color="#c6dfef"/>
      {floors.map(f=><FloorScene key={f.id} geometry={geometry} floorId={f.id} elevation={elevation(f.id)} highlights={roomHighlights} onSpaceClick={onSpaceClick} follow={follow} ceiling={ceiling} span={span}/>)}
      {geometry.spaces.filter(s=>visibleFloors.has(s.floor_id)&&(s.id===emphasis||(highlights.size<=4&&highlights.has(s.id)))).map(s=>{
        const anchor=s.anchor??s.polygon[0];return <group key={`focus-${s.id}`}>
          <Line points={[...s.polygon,s.polygon[0]].map(p=>frame(p[0],p[1],elevation(s.floor_id)+.12))} color="#74c9ef" lineWidth={3} depthTest={false} depthWrite={false} renderOrder={109}/>
          {!follow&&<Html center position={[anchor[0],elevation(s.floor_id)+1.7,-anchor[1]]} style={{pointerEvents:"none"}}><span className="world-label selected-label">{s.name}</span></Html>}
        </group>;
      })}
      {visualResult?.lines?.map((line,i)=>{
        const floor=geometry.floors.find(f=>Math.abs(f.elevation_m-line.a[2])<.01);
        if(floor&&!visibleFloors.has(floor.id))return null;
        return <Line key={`measurement-${i}`} points={[frame(line.a[0],line.a[1],line.a[2]+.15),frame(line.b[0],line.b[1],line.b[2]+.15)]} color="#74c9ef" lineWidth={5} depthTest={false} depthWrite={false} renderOrder={110}/>;
      })}
      {visualResult?.kind==="intervention"&&(()=>{
        const proposed=visualResult.measurements.proposed_opening as Opening|undefined;
        if(!proposed||!visibleFloors.has(proposed.floor_id))return null;
        const alignment=openingFrame(geometry,proposed);if(!alignment)return null;
        return <group position={[alignment.x,elevation(proposed.floor_id)+.8,-alignment.y]} rotation={[0,alignment.angle,0]}><mesh><boxGeometry args={[proposed.width_m,1.6,.06]}/><meshBasicMaterial color="#74c9ef" transparent opacity={.5} depthTest={false}/></mesh><Html center position={[0,1,0]}><span className="world-label">Proposed opening · not applied</span></Html></group>;
      })()}
      {previousRoute&&!follow&&<Path route={previousRoute} geometry={geometry} explode={explode} visibleFloors={visibleFloors} ghost/>}
      {route&&<Path route={route} geometry={geometry} explode={explode} visibleFloors={visibleFloors} xray={false}/>}
      {route?.guide.steps.slice(activeStep+1,activeStep+2).map((s,i)=>s.point&&s.floor_id&&visibleFloors.has(s.floor_id)&&<mesh key={i} position={[s.point[0],elevation(s.floor_id)+0.15,-s.point[1]]}>
        <cylinderGeometry args={[0.38,0.38,0.1,24]}/><meshStandardMaterial color="#ffd45c" emissive="#a66c00" emissiveIntensity={0.5}/></mesh>)}
      {geometry.openings.filter(o=>visibleFloors.has(o.floor_id)&&(closed.has(o.id)||previewDoor?.id===o.id)).map(o=><mesh key={o.id} position={[o.position[0],elevation(o.floor_id)+.6,-o.position[1]]}>
        <boxGeometry args={[Math.max(o.width_m,.3),1.2,.15]}/><meshStandardMaterial color={closed.has(o.id)?"#ff8a8f":"#ffd45c"} emissive={closed.has(o.id)?"#9c202c":"#7c5612"}/></mesh>)}
      {geometry.connectors.filter(c=>closed.has(c.id)).flatMap(c=>c.space_ids.map(id=>geometry.spaces.find(s=>s.id===id)).filter((s):s is Space=>!!s&&visibleFloors.has(s.floor_id))).map(s=>{
        const b=bounds(s.polygon);return <mesh key={s.id} position={[(b.minX+b.maxX)/2,elevation(s.floor_id)+.8,-(b.minY+b.maxY)/2]}><boxGeometry args={[Math.max(b.maxX-b.minX,.5),1.6,Math.max(b.maxY-b.minY,.5)]}/><meshStandardMaterial color="#ff8a8f" transparent opacity={.65}/></mesh>;
      })}
      {here&&geometry.spaces.filter(s=>s.id===here&&visibleFloors.has(s.floor_id)).map(s=>{const point=route?.stops[0]===here?route.polyline[0]:null;const b=bounds(s.polygon);return <group key={s.id} position={[point?.x??s.anchor?.[0]??(b.minX+b.maxX)/2,elevation(s.floor_id)+.08,-(point?.y??s.anchor?.[1]??(b.minY+b.maxY)/2)]}><mesh rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.35,.52,32]}/><meshBasicMaterial color="#65d7ac" side={THREE.DoubleSide} depthTest={false}/></mesh><mesh position={[0,.35,0]}><sphereGeometry args={[.18,16,12]}/><meshStandardMaterial color="#65d7ac" emissive="#1e7a4c"/></mesh>{heading!==undefined&&<group rotation={[0,-heading*Math.PI/180,0]}><mesh position={[0,.15,-.65]} rotation={[-Math.PI/2,0,0]}><coneGeometry args={[.2,.5,3]}/><meshBasicMaterial color="#65d7ac"/></mesh></group>}</group>;})}
      {follow&&route&&model?<RouteCamera geometry={geometry} model={model} clock={clock} playing={playing&&previewMode&&!reduced} speed={speed} seekVersion={seekVersion} onSample={report}/>
        :<><OrbitControls maxPolarAngle={Math.PI/2.03} minDistance={2} maxDistance={span*4} makeDefault/><FitBuilding cacheKey={`${geometry.building.id}-${multi?scope:floorId}-${exploded}-${emphasis??visualResult?.id??"explore"}`} fitVersion={fitVersion} box={fitBox} height={multi?Math.max(...floors.map(f=>elevation(f.id)+f.height_m))-Math.min(...floors.map(f=>elevation(f.id))):3.8} activeElevation={multi?Math.min(...floors.map(f=>elevation(f.id))):elevation(floorId)}/><CameraActions action={action}/></>}
    </Canvas>
    {follow&&sample?.transition&&<div className="landing-transition"><span>⇅</span><b>Use the mapped connector</b><p>{geometry.floors.find(f=>f.id===sample.point?.floor_id)?.name}</p><small>Landing preview · interior geometry not surveyed</small></div>}
    {follow&&route&&model&&<div className="media-dock" aria-label={previewMode?"Route preview player":"Landmark guidance"}>
      <button className="ceiling-toggle" aria-pressed={ceiling} onClick={()=>setCeiling(!ceiling)} title="Illustrative ceiling">Ceiling</button>
      <div className="media-status" role="status">{sample?.arrived?"Destination reached in preview":sample?.transition?`Landing transition - ${geometry.floors.find(f=>f.id===sample.point?.floor_id)?.name} - connector interior not surveyed`:previewMode?"Route preview":"Guide me - location set manually"}</div>
      {previewMode&&<div className="timeline"><input aria-label="Preview progress" type="range" min="0" max={Math.ceil(model.duration*100)/100||1} step="0.01" value={time} onChange={e=>seek(Number(e.target.value))}/><div className="chapter-marks">{model.chapters.map((c,i)=><button key={i} style={{left:`${100*c/(model.duration||1)}%`}} aria-label={`Jump to instruction ${i+1}`} title={route.guide.steps[i].text} onClick={()=>seek(c)}/>)}</div></div>}
      <div className="media-buttons">
        <button aria-label="Previous instruction" disabled={activeStep<=0} onClick={()=>{setPlaying(false);seek(model.chapters[activeStep-1]??0);}}>&#8249;</button>
        {previewMode&&!reduced&&<button className="media-play" aria-label={sample?.arrived?"Replay preview":playing?"Pause preview":"Play preview"} onClick={()=>{if(sample?.arrived)seek(0);setPlaying(v=>sample?.arrived?true:!v);}}>{sample?.arrived?"\u21ba":playing?"\u2161":"\u25b6"}</button>}
        <button aria-label="Next instruction" disabled={sample?.arrived} onClick={()=>{setPlaying(false);seek(model.chapters[Math.min(activeStep+1,model.chapters.length-1)]??model.duration);}}>&#8250;</button>
        {!previewMode&&<button onClick={onRepeat}>Repeat</button>}
        {previewMode?<><span className="media-time">{Math.floor(time/60)}:{String(Math.floor(time%60)).padStart(2,"0")} / {Math.floor(model.duration/60)}:{String(Math.floor(model.duration%60)).padStart(2,"0")}</span><select aria-label="Playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.5,1,2,4].map(v=><option key={v} value={v}>{v}x</option>)}</select></>:<button onClick={onPreview}>Preview route</button>}
        <button onClick={()=>{setPlaying(false);onFinish?.();}}>{sample?.arrived?"Finish":"Exit"}</button>
      </div>
    </div>}

    {!follow&&<div className="scene-navigation" aria-label="3D camera controls">
      {[["fit","Fit","Fit building"],["zoom-in","+","Zoom in"],["zoom-out","−","Zoom out"],["left","←","Pan left"],["right","→","Pan right"],["up","↑","Pan up"],["down","↓","Pan down"]].map(([kind,text,label])=><button key={kind} aria-label={label} onClick={()=>kind==="fit"?setFitVersion(v=>v+1):setAction({id:action.id+1,kind})}>{text}</button>)}
    </div>}
    {!follow&&<div className="scene-caption">{explode?"Exploded floors · 2 m visual separation":"Schematic model · supplied floor elevations and footprints"}<br/><span>Drag to orbit · scroll to zoom · object heights are illustrative</span></div>}
  </div>;
}
export default Building3D;

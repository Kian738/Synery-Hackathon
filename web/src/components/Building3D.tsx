import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { SceneAssets } from "./SceneAssets";
import { SceneLabels, type SceneLabel, type ProjectedLabel } from "./SceneLabels";
import { GuidePlayer } from "./GuidePlayer";
import { ExploreCamera } from "./ExploreCamera";
import { Pictogram } from "./Pictogram";
import { PickIntent } from "../lib/interaction";
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
    onClick={(e:ThreeEvent<MouseEvent>)=>{e.stopPropagation();if(e.delta>5)return;const room=b.ranges.find(r=>(e.faceIndex??0)<r.end);if(room)onPick?.(room.space);}}>
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
  return <group position={[0,elevation,0]}><mesh geometry={mesh} userData={{labelOccluder:true}}><meshStandardMaterial color="#b5c5c6" roughness={0.85} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}/></mesh>
    <lineSegments geometry={edges}><lineBasicMaterial color="#f0f8fa" transparent opacity={0.18}/></lineSegments></group>;
}

function Doorways({geometry,floorId,elevation,follow,activeOpening}:{geometry:Geometry;floorId:string;elevation:number;follow:boolean;activeOpening?:string}) {
  const ref=useRef<THREE.InstancedMesh>(null);
  const parts=useMemo(()=>geometry.openings.filter(o=>o.floor_id===floorId&&Number.isFinite(o.width_m)&&o.width_m>0&&["door","entrance","opening"].includes(o.kind)).flatMap(o=>{
    const alignment=openingFrame(geometry,o);if(!alignment)return [];
    const height=follow?Math.min(2.1,(geometry.floors.find(f=>f.id===floorId)?.height_m??3)-.1):1.25;
    const width=Math.max(.1,o.width_m),color=o.id===activeOpening?"#ffd45c":o.kind==="entrance"?"#66bea0":o.kind==="opening"?"#8cabb7":"#bba786";
    const base={alignment,color};
    const parts=[{...base,x:0,y:.012,w:width,h:.025,d:.22}];
    if(o.kind!=="opening")parts.push(...[-1,1].map(sign=>({...base,x:sign*(width/2+.025),y:height/2,w:.055,h:height,d:.12})),{...base,x:0,y:height,w:width+.1,h:.07,d:.12});
    return parts;
  }),[geometry,floorId,follow,activeOpening]);
  useEffect(()=>{if(!ref.current)return;const parent=new THREE.Object3D(),part=new THREE.Object3D();parts.forEach((p,i)=>{
    parent.position.set(p.alignment.x,0,-p.alignment.y);parent.rotation.y=p.alignment.angle;parent.updateMatrix();
    part.position.set(p.x,p.y,0);part.scale.set(p.w,p.h,p.d);part.updateMatrix();
    ref.current!.setMatrixAt(i,parent.matrix.clone().multiply(part.matrix));ref.current!.setColorAt(i,new THREE.Color(p.color));
  });ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;ref.current.computeBoundingSphere();},[parts]);
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}><boxGeometry/><meshStandardMaterial roughness={.7} metalness={.15}/></instancedMesh></group>;
}

function UpperContext({geometry,above}:{geometry:Geometry;above:number}) {
  const surfaces=useMemo(()=>(geometry.scene?.slabs??[]).flatMap(s=>{
    const floor=geometry.floors.find(f=>f.id===s.floor_id);if(!floor||floor.elevation_m<=above+.05)return [];
    const mesh=new THREE.BufferGeometry();mesh.setAttribute("position",new THREE.Float32BufferAttribute(s.vertices.flatMap(p=>[p[0],floor.elevation_m,-p[1]]),3));mesh.computeVertexNormals();
    return [{floor,mesh}];
  }),[geometry,above]);
  useEffect(()=>()=>surfaces.forEach(s=>s.mesh.dispose()),[surfaces]);
  return <>{surfaces.map(({floor,mesh})=><group key={floor.id}><mesh geometry={mesh}><meshStandardMaterial color="#b2bcb9" roughness={1} side={THREE.DoubleSide}/></mesh><Walls geometry={geometry} floorId={floor.id} elevation={floor.elevation_m} follow/></group>)}</>;
}

const FloorScene=memo(function FloorScene({geometry,floorId,elevation,highlights,onSpaceClick,follow,ceiling,span,connectorSpaces,labelFloor,activeOpening}:{geometry:Geometry;floorId:string;elevation:number;highlights:Set<string>;onSpaceClick?:(s:Space)=>void;follow:boolean;ceiling:boolean;span:number;connectorSpaces:Set<string>;labelFloor:string;activeOpening?:string}) {
  const spaces=useMemo(()=>geometry.spaces.filter(s=>s.floor_id===floorId),[geometry,floorId]);
  const assets=useMemo(()=>geometry.assets.filter(a=>a.floor_id===floorId),[geometry,floorId]);
  const height=geometry.floors.find(f=>f.id===floorId)?.height_m??3;
  const roomHighlights=highlights;
  return <group>
        <Floors spaces={spaces} elevation={elevation} highlights={roomHighlights} onPick={onSpaceClick}/>
        <Walls geometry={geometry} floorId={floorId} elevation={elevation} follow={follow}/>
        <Doorways geometry={geometry} floorId={floorId} elevation={elevation} follow={follow} activeOpening={activeOpening}/>

        {geometry.connectors.flatMap(c=>c.space_ids.map(id=>({c,s:spaces.find(s=>s.id===id)}))).filter(pair=>pair.s).map(({c,s})=>{const b=bounds(s!.polygon);return <group key={s!.id} position={[(b.minX+b.maxX)/2,elevation+.08,-(b.minY+b.maxY)/2]}>
          <mesh rotation={[-Math.PI/2,0,0]}><planeGeometry args={[Math.min(1,b.maxX-b.minX),Math.min(1,b.maxY-b.minY)]}/><meshStandardMaterial color={c.kind==="lift"?"#5e92a4":"#b4a378"}/></mesh>
          {c.kind==="stairs"&&[-.3,0,.3].map(z=><mesh key={z} position={[0,.01,z]}><boxGeometry args={[.8,.015,.04]}/><meshBasicMaterial color="#e6e8e6"/></mesh>)}
        </group>;})}
        <SceneAssets interior={follow} assets={assets.filter(a=>!highlights.has(a.id))} elevation={elevation} highlighted={false} muted={highlights.size>0}/>
        <SceneAssets interior={follow} assets={assets.filter(a=>highlights.has(a.id))} elevation={elevation} highlighted/>
  </group>;
});

function Path({route,geometry,explode=0,ghost=false,xray=false,visibleFloors}:{route:Route;geometry:Geometry;explode?:number;ghost?:boolean;xray?:boolean;visibleFloors:Set<string>}){
  const meshes=useMemo(()=>routeRuns(route,visibleFloors).map(run=>{
    const points=run.map(p=>{const f=geometry.floors.find(f=>f.id===p.floor_id);return frame(p.x,p.y,(f?.elevation_m??0)+(f?.level??0)*explode+(ghost?.03:.075));});
    const vertices:number[]=[],radius=ghost?.055:.08;
    for(let i=1;i<points.length;i++){
      const a=points[i-1],b=points[i],delta=b.clone().sub(a);if(delta.length()<1e-6)continue;
      const n=new THREE.Vector3(-delta.z,0,delta.x).normalize().multiplyScalar(radius);
      const l=a.clone().add(n),r=a.clone().sub(n),u=b.clone().add(n),v=b.clone().sub(n);
      for(const p of [l,r,u,r,v,u])vertices.push(p.x,p.y,p.z);
    }
    for(const p of points)for(let k=0;k<12;k++)for(const v of [p,new THREE.Vector3(p.x+radius*Math.cos(k*Math.PI/6),p.y,p.z+radius*Math.sin(k*Math.PI/6)),new THREE.Vector3(p.x+radius*Math.cos((k+1)*Math.PI/6),p.y,p.z+radius*Math.sin((k+1)*Math.PI/6))])vertices.push(v.x,v.y,v.z);
    const mesh=new THREE.BufferGeometry();mesh.setAttribute("position",new THREE.Float32BufferAttribute(vertices,3));mesh.computeVertexNormals();return mesh;
  }),[route,geometry,explode,visibleFloors,ghost]);
  useEffect(()=>()=>meshes.forEach(m=>m.dispose()),[meshes]);
  return <>{meshes.map((g,i)=><mesh key={i} geometry={g} renderOrder={ghost?1:2}><meshBasicMaterial color={ghost?"#869ba5":"#ffd45c"} side={THREE.DoubleSide} transparent={ghost} opacity={ghost?.3:1} depthWrite={false} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-2}/></mesh>)}</>;
}


function RouteCamera({geometry,model,clock,playing,speed,seekVersion,onSample,lookOffset}:{geometry:Geometry;model:Presentation;clock:MutableRefObject<number>;playing:boolean;speed:number;seekVersion:number;onSample:(time:number)=>void;lookOffset?:{yaw:number;pitch:number}}){
  const {camera,invalidate,gl,scene}=useThree();const sight=useMemo(()=>new THREE.Raycaster(),[]);const lastReport=useRef(-1);const first=useRef(true);const lastTick=useRef(performance.now());
  useLayoutEffect(()=>{lastTick.current=performance.now();},[playing]);
  useEffect(()=>{first.current=true;invalidate();},[seekVersion,model,invalidate]);
  useEffect(()=>{invalidate();},[lookOffset,invalidate]);
  useFrame((_,dt)=>{
    const now=performance.now(),elapsed=Math.max(0,(now-lastTick.current)/1000);lastTick.current=now;
    if(playing)clock.current=advancePreview(clock.current,elapsed,speed,model.duration);
    const sample=samplePreview(model,clock.current),p=sample.point;if(!p)return;
    const height=geometry.floors.find(f=>f.id===p.floor_id)?.elevation_m??0;
    camera.position.copy(frame(p.x,p.y,height+1.65));
    // Look along the visible route ahead, rather than staring along each tiny raster edge.
    // Walls constrain the viewing target; this changes orientation only, never walking geometry.
    const walls:THREE.Object3D[]=[];scene.traverse(o=>{if(o.userData.labelOccluder)walls.push(o);});
    let direction=new THREE.Vector3(sample.heading[0],0,-sample.heading[1]);
    for(const seconds of [2,1.25,.75,.25]){
      const ahead=samplePreview(model,Math.min(model.duration,clock.current+seconds));
      if(sample.transition||ahead.transition||ahead.point?.floor_id!==p.floor_id)continue;
      const v=new THREE.Vector3(ahead.point.x-p.x,0,-(ahead.point.y-p.y)),distance=v.length();
      if(distance<.05)continue;
      sight.set(camera.position,v.clone().normalize());sight.near=0;sight.far=Math.max(0,distance-.04);
      if(!sight.intersectObjects(walls,false).length){direction=v;break;}
    }
    direction.y=-direction.length()*.14;
    if(direction.lengthSq()>.00001){
      const matrix=new THREE.Matrix4().lookAt(camera.position,camera.position.clone().add(direction),new THREE.Vector3(0,1,0));
      const target=new THREE.Quaternion().setFromRotationMatrix(matrix);
      if(lookOffset)target.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(lookOffset.pitch),-THREE.MathUtils.degToRad(lookOffset.yaw),0,"YXZ")));
      if(first.current)camera.quaternion.copy(target);else camera.quaternion.rotateTowards(target,Math.min(camera.quaternion.angleTo(target)*(1-Math.exp(-5*dt)),Math.PI*.65*dt));
      if(camera.quaternion.angleTo(target)>.002)invalidate();
      first.current=false;
    }
    camera.updateProjectionMatrix();gl.domElement.dataset.cameraPosition=JSON.stringify(camera.position.toArray());gl.domElement.dataset.cameraFloor=p.floor_id;gl.domElement.dataset.cameraQuaternion=JSON.stringify(camera.quaternion.toArray());
    if(Math.abs(clock.current-lastReport.current)>.08 || sample.arrived || !playing){lastReport.current=clock.current;onSample(clock.current);}
    if(playing)invalidate();
  });return null;
}

export function Building3D({geometry,floorId,route,previousRoute,highlights=new Set(),closed=new Set(),previewDoor,showAll,scope="current",exploded=true,follow=false,previewMode=true,activeStep=0,seekRequest=0,onStep,onSpaceClick,onFinish,onPreview,here,selected,visualResult,onPosition,heading,onRepeat,focusRequest,lookOffset}: {
 geometry:Geometry;floorId:string;route?:Route|null;previousRoute?:Route|null;highlights?:Set<string>;closed?:Set<string>;previewDoor?:Opening|null;
 lookOffset?:{yaw:number;pitch:number};focusRequest?:{id:string;revision:number}|null;onRepeat?:()=>void;heading?:number;visualResult?:VisualResult|null;onPosition?:(p:{x:number;y:number;floor_id:string})=>void;showAll:boolean;scope?:"current"|"route"|"building";exploded?:boolean;previewMode?:boolean;seekRequest?:number;onFinish?:()=>void;onPreview?:()=>void;here?:string|null;selected?:string|null;follow?:boolean;activeStep?:number;onStep?:(i:number)=>void;onSpaceClick?:(s:Space)=>void;
}){
  const stageRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{const el=stageRef.current;if(!el)return;const wheel=(e:WheelEvent)=>{if(e.ctrlKey)e.preventDefault();};const gesture=(e:Event)=>e.preventDefault();el.addEventListener("wheel",wheel,{passive:false,capture:true});el.addEventListener("gesturestart",gesture,{passive:false});el.addEventListener("gesturechange",gesture,{passive:false});return()=>{el.removeEventListener("wheel",wheel,true);el.removeEventListener("gesturestart",gesture);el.removeEventListener("gesturechange",gesture);};},[]);
  const reduced=typeof matchMedia!=="undefined"&&matchMedia("(prefers-reduced-motion: reduce)").matches;
  const emphasis=focusRequest?.id??(visualResult?.measurements.primary_ids as string[]|undefined)?.[0];
  const [action,setAction]=useState({id:0,kind:""});
  const ceiling=true;
  const [orbiting,setOrbiting]=useState(false);
  const gesture=useRef(new PickIntent());
  const pick=useCallback((space:Space)=>{if(!follow&&!gesture.current.moved)onSpaceClick?.(space);},[onSpaceClick,follow]);
  const [fitVersion,setFitVersion]=useState(0);
  const [playing,setPlaying]=useState(false),[time,setTime]=useState(0),[speed,setSpeed]=useState(1),[seekVersion,setSeekVersion]=useState(0);
  const clock=useRef(0), model=useMemo(()=>route?presentation(route):null,[route]);
  const sample=model?samplePreview(model,time):null;
  const connectorSpaces=useMemo(()=>new Set([...(route?.polyline.map(p=>p.node)??[]),...(selected?[selected]:[])]),[route,selected]);
  const activeOpening=useMemo(()=>{
    if(!follow||!route)return undefined;
    const point=route.guide.steps[activeStep]?.point??route.guide.steps[activeStep+1]?.point;
    const floor=route.guide.steps[activeStep]?.floor_id;
    return point?geometry.openings.find(o=>o.floor_id===floor&&Math.hypot(o.position[0]-point[0],o.position[1]-point[1])<.5)?.id:undefined;
  },[geometry,route,follow,activeStep]);
  const seek=(value:number)=>{value=Math.max(0,Math.min(value,model?.duration??0));clock.current=value;setTime(value);setSeekVersion(v=>v+1);};
  useEffect(()=>{seek(0);setPlaying(false);},[route,follow]);
  useEffect(()=>{if(!previewMode)setPlaying(false);},[previewMode]);
  useEffect(()=>{const pause=()=>setPlaying(false);window.addEventListener("floorwise:voice-start",pause);return()=>window.removeEventListener("floorwise:voice-start",pause);},[]);
  useEffect(()=>{if(model){setPlaying(false);seek(model.chapters[activeStep]??0);}},[seekRequest]);
  useEffect(()=>{const hidden=()=>{if(document.hidden)setPlaying(false);};document.addEventListener("visibilitychange",hidden);return()=>document.removeEventListener("visibilitychange",hidden);},[]);
  useEffect(()=>{if(!follow)return;const key=(e:KeyboardEvent)=>{if(e.defaultPrevented||/INPUT|SELECT|TEXTAREA|BUTTON/.test((e.target as HTMLElement)?.tagName))return;if(e.code==="Space"&&!reduced){e.preventDefault();if(!previewMode)onPreview?.();if(clock.current>=(model?.duration??Infinity))seek(0);setPlaying(v=>!v);}if(e.code==="ArrowRight"||e.code==="ArrowLeft"){e.preventDefault();seek(Math.max(0,Math.min(model?.duration??0,clock.current+(e.code==="ArrowRight"?5:-5))));}};window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);},[follow,previewMode,model,reduced,onPreview]);
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
  const [projectedLabels,setProjectedLabels]=useState<ProjectedLabel[]>([]);
  const sceneLabels=useMemo<SceneLabel[]>(()=>follow?[]:[
    ...geometry.connectors.flatMap(c=>c.space_ids.flatMap(id=>{const s=geometry.spaces.find(s=>s.id===id&&s.floor_id===floorId);if(!s||!visibleFloors.has(s.floor_id)||!connectorSpaces.has(id))return [];const b=bounds(s.polygon);return [{id:`connector-${id}`,text:c.name,icon:c.kind,position:[(b.minX+b.maxX)/2,elevation(s.floor_id)+.7,-(b.minY+b.maxY)/2] as [number,number,number]}];})),
    ...geometry.spaces.filter(s=>visibleFloors.has(s.floor_id)&&(s.id===emphasis||(highlights.size<=4&&highlights.has(s.id)))).map(s=>{const p=s.anchor??s.polygon[0];return {id:`room-${s.id}`,text:s.name,position:[p[0],elevation(s.floor_id)+1.7,-p[1]] as [number,number,number]};}),
    ...(visualResult?.kind==="intervention"?(()=>{const o=visualResult.measurements.proposed_opening as Opening|undefined;return o&&visibleFloors.has(o.floor_id)?[{id:"proposed",text:"Proposed opening · not applied",position:[o.position[0],elevation(o.floor_id)+1.8,-o.position[1]] as [number,number,number]}]:[];})():[])
  ],[geometry,follow,floorId,visibleFloors,connectorSpaces,emphasis,highlights,visualResult,explode]);

  return <div ref={stageRef} className="building-stage" onPointerDownCapture={e=>gesture.current.begin(e.clientX,e.clientY)} onPointerMoveCapture={e=>gesture.current.move(e.clientX,e.clientY)} onPointerCancelCapture={()=>gesture.current.cancel()} data-testid="building-scene" data-scene-revision={geometry.scene?.revision} data-ceiling-source="upper-floor-footprints" data-context-floors={follow?geometry.floors.filter(f=>f.elevation_m>elevation(activeFloor)+.05).map(f=>f.id).join(","):""} data-visible-floors={[...visibleFloors].join(",")} data-playback-state={sample?.arrived?"arrived":sample?.transition?"transition":playing?"playing":time?"paused":"idle"}>
    <Canvas frameloop={playing&&previewMode&&!reduced?"always":"demand"} dpr={[1,1.5]} camera={{position:[cx+span*.65,span*.8,cz+span*.8],fov:follow?70:40,near:follow?.06:.5,far:Math.max(200,span*6)}} gl={{antialias:true}}
      onCreated={({gl})=>{gl.setClearColor("#10171c");}}>
      <ambientLight intensity={follow?1.3:.65}/><hemisphereLight args={["#edf5ff","#59645c",follow?1.5:1.1]}/>
      <directionalLight position={[cx+30,80,cz+40]} intensity={1.7}/><directionalLight position={[cx-30,20,cz-25]} intensity={.6} color="#c6dfef"/>
      {follow&&<UpperContext geometry={geometry} above={elevation(activeFloor)}/>}
      {floors.map(f=><FloorScene key={f.id} geometry={geometry} floorId={f.id} elevation={elevation(f.id)} highlights={roomHighlights} onSpaceClick={pick} follow={follow} ceiling={ceiling} span={span} connectorSpaces={connectorSpaces} labelFloor={floorId} activeOpening={activeOpening}/>)}
      {geometry.spaces.filter(s=>visibleFloors.has(s.floor_id)&&(s.id===emphasis||(highlights.size<=4&&highlights.has(s.id)))).map(s=>{
        const anchor=s.anchor??s.polygon[0];return <group key={`focus-${s.id}`}>
          <Line points={[...s.polygon,s.polygon[0]].map(p=>frame(p[0],p[1],elevation(s.floor_id)+.12))} color="#74c9ef" lineWidth={3} depthTest={false} depthWrite={false} renderOrder={109}/>
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
        return <group position={[alignment.x,elevation(proposed.floor_id)+.8,-alignment.y]} rotation={[0,alignment.angle,0]}><mesh><boxGeometry args={[proposed.width_m,1.6,.06]}/><meshBasicMaterial color="#74c9ef" transparent opacity={.5} depthTest={false}/></mesh></group>;
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
      {here&&geometry.spaces.filter(s=>s.id===here&&visibleFloors.has(s.floor_id)).map(s=>{const point=route?.stops[0]===here?route.polyline[0]:null;const b=bounds(s.polygon);return <group key={s.id} position={[point?.x??s.anchor?.[0]??(b.minX+b.maxX)/2,elevation(s.floor_id)+.08,-(point?.y??s.anchor?.[1]??(b.minY+b.maxY)/2)]}><mesh rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.14,.22,24]}/><meshBasicMaterial color="#65d7ac" side={THREE.DoubleSide} depthTest={false}/></mesh><mesh position={[0,.12,0]}><sphereGeometry args={[.1,12,8]}/><meshStandardMaterial color="#65d7ac" emissive="#1e7a4c"/></mesh>{heading!==undefined&&<group rotation={[0,-heading*Math.PI/180,0]}><mesh position={[0,.15,-.65]} rotation={[-Math.PI/2,0,0]}><coneGeometry args={[.2,.5,3]}/><meshBasicMaterial color="#65d7ac"/></mesh></group>}</group>;})}
      {follow&&route&&model?<RouteCamera geometry={geometry} model={model} clock={clock} playing={playing&&previewMode&&!reduced} speed={speed} seekVersion={seekVersion} onSample={report} lookOffset={lookOffset}/>
        :<><OrbitControls mouseButtons={{LEFT:orbiting?THREE.MOUSE.ROTATE:THREE.MOUSE.PAN,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.ROTATE}} touches={{ONE:THREE.TOUCH.PAN,TWO:THREE.TOUCH.DOLLY_ROTATE}} maxPolarAngle={Math.PI/2.03} minDistance={2} maxDistance={span*4} makeDefault/><ExploreCamera remoteLook={lookOffset} cacheKey={`${geometry.building.id}-${multi?scope:floorId}-${exploded}-${focusRequest?`${focusRequest.id}-${focusRequest.revision}`:visualResult?.id??"explore"}`} fitVersion={fitVersion} box={fitBox} height={multi?Math.max(...floors.map(f=>elevation(f.id)+f.height_m))-Math.min(...floors.map(f=>elevation(f.id))):3.8} elevation={multi?Math.min(...floors.map(f=>elevation(f.id))):elevation(floorId)} action={action}/></>}

      <SceneLabels labels={sceneLabels} onProject={setProjectedLabels}/>
    </Canvas>
    {!follow&&<div className="scene-label-layer">{projectedLabels.map(l=><div key={l.id} style={{position:"absolute",left:l.x,top:l.y,transform:"translate(-50%,-50%)"}}>{l.icon?<span className="connector-icon" title={l.text}><Pictogram name={l.icon} size={17}/></span>:<span className="world-label selected-label">{l.text}</span>}</div>)}</div>}
    {follow&&sample?.transition&&<div className="landing-transition"><span>⇅</span><b>Use the mapped connector</b><p>{geometry.floors.find(f=>f.id===sample.point?.floor_id)?.name}</p><small>Landing preview · interior geometry not surveyed</small></div>}
    {follow&&route&&model&&<GuidePlayer route={route} model={model} time={time} speed={speed} playing={playing} step={activeStep} reduced={reduced} transition={sample?.transition?"Floor transition":null}
      onSeek={seek} onPlay={()=>{if(!previewMode)onPreview?.();if(sample?.arrived)seek(0);setPlaying(v=>sample?.arrived?true:!v);}}
      onPrevious={()=>{setPlaying(false);seek(model.chapters[activeStep-1]??0);}} onNext={()=>{setPlaying(false);seek(model.chapters[Math.min(activeStep+1,model.chapters.length-1)]??model.duration);}}
      onSpeed={setSpeed} onRepeat={onRepeat} onExit={()=>{setPlaying(false);onFinish?.();}}/>}
    {!follow&&<div className="scene-navigation" aria-label="3D camera controls">
      <button aria-label={orbiting?"Move building":"Rotate building"} aria-pressed={orbiting} title={orbiting?"Drag to rotate (right-drag also rotates)":"Drag to move; right-drag to rotate"} onClick={()=>setOrbiting(!orbiting)}><Pictogram name={orbiting?"orbit":"hand"}/></button>
      <button aria-label="Fit building" title="Fit building" onClick={()=>setFitVersion(v=>v+1)}><Pictogram name="fit"/></button>
      <button aria-label="Zoom in" title="Zoom in" onClick={()=>setAction(v=>({id:v.id+1,kind:"zoom-in"}))}><Pictogram name="plus"/></button>
      <button aria-label="Zoom out" title="Zoom out" onClick={()=>setAction(v=>({id:v.id+1,kind:"zoom-out"}))}><Pictogram name="minus"/></button>
    </div>}
    {!follow&&<details className="scene-info"><summary aria-label="Model details"><Pictogram name="info" size={18}/></summary><p>Schematic model from supplied footprints and floor elevations. Object appearance is illustrative.{explode?" Floors are separated by 2 m for inspection.":""}</p><p>Drag to move · right-drag to rotate · scroll to zoom.</p></details>}
  </div>;

}
export default Building3D;

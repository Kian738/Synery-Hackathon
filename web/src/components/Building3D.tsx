import { Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { bounds, zoneOf } from "../lib/geometry";
import type { Asset, Geometry, Opening, Route, Space } from "../lib/types";

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
  return <group position={[0,elevation,0]}>{batches.map(b=>b.geometry&&<mesh key={b.zone} geometry={b.geometry}
    onClick={(e:ThreeEvent<MouseEvent>)=>{e.stopPropagation();const room=b.ranges.find(r=>(e.faceIndex??0)<r.end);if(room)onPick?.(room.space);}}>
    <meshStandardMaterial color={b.zone==="highlight"?"#ffd45c":COLORS[b.zone]??COLORS.office} roughness={0.94} side={THREE.DoubleSide}/>
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
  return <group position={[0,elevation,0]}><mesh geometry={mesh}><meshStandardMaterial color="#c3d2d5" roughness={0.85} side={THREE.DoubleSide}/></mesh>
    <lineSegments geometry={edges}><lineBasicMaterial color="#f0f8fa" transparent opacity={0.35}/></lineSegments></group>;
}

function assetStyle(a:Asset){
  if(/coffee|printer|fridge|cabinet|locker|shelf|rack/.test(a.type))return {height:1.5,color:"#344c58"};
  if(/table|desk|bench|counter/.test(a.type))return {height:0.76,color:"#b39a74"};
  if(/chair|sofa|bed/.test(a.type))return {height:0.65,color:"#536b7c"};
  if(a.category==="machine")return {height:1.65,color:"#577e87"};
  return {height:0.85,color:"#9badad"};
}
function FurnitureBatch({assets,elevation,highlighted}:{assets:Asset[];elevation:number;highlighted:boolean}){
  const ref=useRef<THREE.InstancedMesh>(null);
  const parts=useMemo(()=>assets.flatMap(a=>{
    const look=assetStyle(a);
    const base={asset:a,color:look.color};
    const box=(x:number,y:number,z:number,w:number,h:number,d:number,color=look.color)=>({...base,x,y,z,w,h,d,color});
    if(/table|desk|bench|counter/.test(a.type))return [box(0,.75,0,1,.08,1),...[-.4,.4].flatMap(x=>[-.4,.4].map(z=>box(x,.35,z,.08,.7,.08,"#49565d")))];
    if(/chair|seat|stool/.test(a.type))return [box(0,.43,0,.9,.1,.85),box(0,.72,-.4,.9,.5,.1),box(0,.2,0,.3,.4,.3,"#3c4b54")];
    if(/coffee/.test(a.type))return [box(0,.5,0,1,1,1),box(0,1.2,-.1,.9,.5,.7,"#233841"),box(0,.95,.38,.6,.1,.2,"#d1dce0")];
    if(a.category==="machine")return [box(0,.15,0,1,.3,1,"#354d57"),box(0,.9,0,.85,1.2,.85),box(.3,1.55,.3,.25,.25,.25,"#ccd8d9")];
    if(/shelf|rack|bookshelf/.test(a.type))return [box(-.45,.85,0,.1,1.7,1),box(.45,.85,0,.1,1.7,1),...[.1,.65,1.2,1.7].map(y=>box(0,y,0,1,.07,1))];
    return [box(0,look.height/2,0,1,look.height,1)];
  }),[assets]);
  useEffect(()=>{if(!ref.current)return;const parent=new THREE.Object3D(),o=new THREE.Object3D();parts.forEach((p,i)=>{
    const a=p.asset,w=a.footprint?.width_m??.5,d=a.footprint?.depth_m??.5;
    parent.position.set(a.position[0],0,-a.position[1]);parent.rotation.set(0,(a.footprint?.rotation_deg??0)*Math.PI/180,0);parent.updateMatrix();
    o.position.set(p.x*w,p.y,p.z*d);o.scale.set(p.w*w,p.h,p.d*d);o.updateMatrix();
    ref.current!.setMatrixAt(i,parent.matrix.clone().multiply(o.matrix));ref.current!.setColorAt(i,new THREE.Color(highlighted?"#ffd45c":p.color));
  });ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;
  ref.current.computeBoundingSphere();},[parts,highlighted]);
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}><boxGeometry/>
    <meshStandardMaterial roughness={0.75} metalness={0.15}/></instancedMesh></group>;
}

function Path({route,geometry,explode=0,ghost=false,xray=true}:{route:Route;geometry:Geometry;explode?:number;ghost?:boolean;xray?:boolean}){
  const runs=useMemo(()=>{
    const out:THREE.Vector3[][]=[];let run:THREE.Vector3[]=[];let previousFloor="";
    for(const p of route.polyline){
      if(run.length&&(p.gap||p.floor_id!==previousFloor)){if(run.length>1)out.push(run);run=[];}
      previousFloor=p.floor_id;const f=geometry.floors.find(f=>f.id===p.floor_id);run.push(frame(p.x,p.y,(f?.elevation_m??0)+(f?.level??0)*explode+0.09));
    }if(run.length>1)out.push(run);return out;
  },[route,geometry,explode]);
  return <>{runs.map((r,i)=><group key={i}>
    <Line points={r} color={ghost?"#91a6b1":"#10171c"} lineWidth={ghost?3:10} depthTest={!xray} depthWrite={false} renderOrder={100} transparent opacity={ghost?0.35:1}/>
    {!ghost&&<Line points={r} color="#ffd45c" lineWidth={5} depthTest={!xray} depthWrite={false} renderOrder={101} transparent opacity={1}/>} 
  </group>)}</>;

}

function FitBuilding({box,height,activeElevation}:{box:{minX:number;maxX:number;minY:number;maxY:number};height:number;activeElevation:number}) {
  const {camera,controls,size,invalidate}=useThree();
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const target=new THREE.Vector3((box.minX+box.maxX)/2,activeElevation+height/2,-(box.minY+box.maxY)/2);
    const radius=Math.hypot(box.maxX-box.minX,box.maxY-box.minY,height)/2;
    const vertical=40*Math.PI/180,horizontal=2*Math.atan(Math.tan(vertical/2)*size.width/size.height);
    const distance=radius/Math.sin(Math.min(vertical,horizontal)/2)*1.12;
    camera.position.copy(target).add(new THREE.Vector3(.65,.8,.8).normalize().multiplyScalar(distance));
    c.target.copy(target);c.update();invalidate();
  },[box,height,activeElevation,camera,controls,size.width,size.height,invalidate]);return null;
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

function RouteCamera({geometry,route,playing,setPlaying,activeStep,onStep,jump,onTransition}:{geometry:Geometry;route:Route;playing:boolean;setPlaying:(v:boolean)=>void;activeStep:number;onStep?:(i:number)=>void;jump:number;onTransition:(s:string)=>void}){
  const {camera,invalidate,gl}=useThree();const cursor=useRef(0);const distance=useRef(0);const previousJump=useRef(jump);
  const points=useMemo(()=>route.polyline.map(p=>({...p,v:frame(p.x,p.y,(geometry.floors.find(f=>f.id===p.floor_id)?.elevation_m??0)+1.65)})),[route,geometry]);
  const steps=useMemo(()=>route.guide.steps.map(s=>{
    let best=0, score=Infinity;points.forEach((p,i)=>{if(s.point&&p.floor_id===s.floor_id){const d=Math.hypot(p.x-s.point[0],p.y-s.point[1]);if(d<score){score=d;best=i;}}});return best;
  }),[points,route]);
  useEffect(()=>{cursor.current=steps[activeStep]??0;distance.current=0;invalidate();},[activeStep,steps,invalidate]);
  useEffect(()=>{if(previousJump.current!==jump){cursor.current=Math.min(cursor.current+1,points.length-1);distance.current=0;previousJump.current=jump;const step=route.guide.steps.findIndex(s=>s.floor_id===points[cursor.current]?.floor_id);if(step>=0)onStep?.(step);invalidate();}},[jump,points,invalidate]);
  useFrame((_,dt)=>{
    const i=cursor.current,a=points[i],b=points[i+1];if(!a)return;
    let position=a.v.clone();
    const heading = i>0 ? a.v.clone().sub(points[i-1].v) : new THREE.Vector3(0,0,-1);
    if(b){
      const gap=b.gap||a.floor_id!==b.floor_id;
      if(gap){if(playing){setPlaying(false);onTransition(`Continue via the mapped stairs or lift to ${geometry.floors.find(f=>f.id===b.floor_id)?.name??"the next section"}. Connector interior is schematic.`);}}
      else {
        const length=a.v.distanceTo(b.v);
        if(playing)distance.current+=Math.min(dt,0.1)*1.6;
        const t=length?Math.min(distance.current/length,1):1;position.lerp(b.v,t);
        if(t>=1&&playing){cursor.current++;distance.current=0;const step=steps.indexOf(cursor.current);if(step>0)onStep?.(step);}
        const forward=b.v.clone().sub(a.v);if(forward.length()>0.01)heading.copy(forward);
      }
    } else if(playing){setPlaying(false);onTransition("You have reached the destination in this preview.");}
    let lookIndex=i+1,remaining=2.5;
    while(lookIndex<points.length && !points[lookIndex].gap && points[lookIndex].floor_id===a.floor_id){
      const segment=points[lookIndex].v.distanceTo(points[lookIndex-1].v);
      remaining-=segment;
      heading.copy(points[lookIndex].v).sub(position);
      if(remaining<=0)break;
      lookIndex++;
    }
    heading.y=0;if(heading.length()<0.01)heading.set(0,0,-1);
    camera.position.copy(position);camera.up.set(0,1,0);camera.lookAt(position.clone().add(heading.normalize().multiplyScalar(3)));camera.updateProjectionMatrix();gl.domElement.dataset.cameraPosition=JSON.stringify(position.toArray());gl.domElement.dataset.cameraFloor=a.floor_id;if(playing)invalidate();
  });
  return null;
}

export function Building3D({geometry,floorId,route,previousRoute,highlights=new Set(),closed=new Set(),previewDoor,showAll,follow=false,activeStep=0,onStep,onSpaceClick}: {
 geometry:Geometry;floorId:string;route?:Route|null;previousRoute?:Route|null;highlights?:Set<string>;closed?:Set<string>;previewDoor?:Opening|null;
 showAll:boolean;follow?:boolean;activeStep?:number;onStep?:(i:number)=>void;onSpaceClick?:(s:Space)=>void;
}){
  const [action,setAction]=useState({id:0,kind:""});
  const [playing,setPlaying]=useState(false),[transition,setTransition]=useState(""),[jump,setJump]=useState(0);
  const reduced=typeof matchMedia!=="undefined"&&matchMedia("(prefers-reduced-motion: reduce)").matches;
  const box=useMemo(()=>bounds(geometry.spaces.flatMap(s=>s.polygon)),[geometry]);
  const cx=(box.minX+box.maxX)/2,cz=-(box.minY+box.maxY)/2,span=Math.max(box.maxX-box.minX,box.maxY-box.minY,10);
  const explode=showAll&&!follow?2:0;
  const elevation=(id:string)=>{const f=geometry.floors.find(f=>f.id===id);return (f?.elevation_m??0)+(f?.level??0)*explode;};
  const floors=showAll&&!follow?geometry.floors:geometry.floors.filter(f=>f.id===(follow&&route?route.guide.steps[activeStep]?.floor_id??floorId:floorId));
  useEffect(()=>{setPlaying(false);setTransition("");},[route,follow]);
  return <div className="building-stage" data-testid="building-scene" data-scene-revision={geometry.scene?.revision}>
    <Canvas frameloop={playing?"always":"demand"} dpr={[1,1.5]} camera={{position:[cx+span*.65,span*.8,cz+span*.8],fov:follow?65:40,near:.05,far:span*25}} gl={{antialias:true}}
      onCreated={({gl})=>{gl.setClearColor("#10171c");}}>
      <ambientLight intensity={0.8}/><hemisphereLight args={["#deefff","#24353a",1.5]}/>
      <directionalLight position={[cx+30,80,cz+40]} intensity={2.4}/>
      {floors.map(f=>{const spaces=geometry.spaces.filter(s=>s.floor_id===f.id),assets=geometry.assets.filter(a=>a.floor_id===f.id);return <group key={f.id}>
        <Floors spaces={spaces} elevation={elevation(f.id)} highlights={highlights} onPick={onSpaceClick}/>
        <Walls geometry={geometry} floorId={f.id} elevation={elevation(f.id)} follow={follow}/>
        <FurnitureBatch assets={assets.filter(a=>!highlights.has(a.id))} elevation={elevation(f.id)} highlighted={false}/>
        <FurnitureBatch assets={assets.filter(a=>highlights.has(a.id))} elevation={elevation(f.id)} highlighted/>
      </group>;})}
      {previousRoute&&!follow&&<Path route={previousRoute} geometry={geometry} explode={explode} ghost/>}
      {route&&<Path route={route} geometry={geometry} explode={explode} xray={!follow}/>}
      {route?.guide.steps.slice(activeStep+1,activeStep+2).map((s,i)=>s.point&&s.floor_id&&<mesh key={i} position={[s.point[0],elevation(s.floor_id)+0.15,-s.point[1]]}>
        <cylinderGeometry args={[0.38,0.38,0.1,24]}/><meshStandardMaterial color="#ffd45c" emissive="#a66c00" emissiveIntensity={0.5}/></mesh>)}
      {geometry.openings.filter(o=>closed.has(o.id)||previewDoor?.id===o.id).map(o=><mesh key={o.id} position={[o.position[0],elevation(o.floor_id)+.6,-o.position[1]]}>
        <boxGeometry args={[Math.max(o.width_m,.3),1.2,.15]}/><meshStandardMaterial color={closed.has(o.id)?"#ff8a8f":"#ffd45c"} emissive={closed.has(o.id)?"#9c202c":"#7c5612"}/></mesh>)}
      {geometry.connectors.filter(c=>closed.has(c.id)).flatMap(c=>c.space_ids.map(id=>geometry.spaces.find(s=>s.id===id)).filter((s):s is Space=>!!s)).map(s=>{
        const b=bounds(s.polygon);return <mesh key={s.id} position={[(b.minX+b.maxX)/2,elevation(s.floor_id)+.8,-(b.minY+b.maxY)/2]}><boxGeometry args={[Math.max(b.maxX-b.minX,.5),1.6,Math.max(b.maxY-b.minY,.5)]}/><meshStandardMaterial color="#ff8a8f" transparent opacity={.65}/></mesh>;
      })}
      {follow&&route?<RouteCamera geometry={geometry} route={route} playing={playing&&!reduced} setPlaying={setPlaying} activeStep={activeStep} onStep={onStep} jump={jump} onTransition={setTransition}/>
        :<><OrbitControls target={[cx,elevation(floorId),cz]} maxPolarAngle={Math.PI/2.03} minDistance={2} maxDistance={span*4} makeDefault/><FitBuilding box={box} height={showAll?Math.max(...geometry.floors.map(f=>elevation(f.id)+f.height_m))-Math.min(...geometry.floors.map(f=>elevation(f.id))):3.8} activeElevation={showAll?Math.min(...geometry.floors.map(f=>elevation(f.id))):elevation(floorId)}/><CameraActions action={action}/></>}
    </Canvas>
    {follow&&route&&<div className="playback-controls"><span>Route preview · position is manually set</span>
      {transition&&<p role="status">{transition}</p>}
      <div><button disabled={activeStep<=0} onClick={()=>{setPlaying(false);onStep?.(activeStep-1);}}>Previous</button>
      {!reduced&&<button onClick={()=>{setTransition("");setPlaying(!playing);}}>{playing?"Pause preview":"Play preview"}</button>}
      {transition&&<button onClick={()=>{setJump(jump+1);setTransition("");}}>Continue at landing</button>}
      <button disabled={activeStep>=route.guide.steps.length-1} onClick={()=>{setPlaying(false);setTransition("");onStep?.(activeStep+1);}}>Next waypoint</button></div>
    </div>}
    {!follow&&<div className="scene-navigation" aria-label="3D camera controls">
      {[["zoom-in","+","Zoom in"],["zoom-out","−","Zoom out"],["left","←","Pan left"],["right","→","Pan right"],["up","↑","Pan up"],["down","↓","Pan down"]].map(([kind,text,label])=><button key={kind} aria-label={label} onClick={()=>setAction({id:action.id+1,kind})}>{text}</button>)}
    </div>}
    {!follow&&<div className="scene-caption">Schematic model · floor elevations and footprints from JSON<br/><span>Drag to orbit · scroll to zoom · object heights are illustrative</span></div>}
  </div>;
}
export default Building3D;

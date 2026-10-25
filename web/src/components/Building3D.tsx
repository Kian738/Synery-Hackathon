import { Line, OrbitControls, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { createContext, memo, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { SceneAssets } from "./SceneAssets";
import { Beacons, type BeaconPoint } from "./Beacons";
import { XR } from "@react-three/xr";
import { VrRig } from "./VrRig";
import { vrPose, xrStore } from "../lib/xr";
import { guideCard } from "../lib/guideCard";
import { orientedRect } from "./Connectors3D";
import { floorColor } from "../lib/floorColors";
import { relevantSpaces, shaftVoids, ease } from "../lib/focus";
import { cameraPath, type Door } from "../lib/cameraPath";
import { SceneLighting } from "./SceneLighting";
import { Roofs } from "./Ceilings";
import { PerfProbe } from "./PerfProbe";
import { DetailWatcher, type Detail } from "./DetailWatcher";
import { Dock, IconButton, Popover } from "../ui/kit";
import { LiftShafts, rideState } from "./LiftShafts";
import { Connectors3D, inside as insidePolygon, stairWalkFor, type WalkPoint } from "./Connectors3D";
import { SceneLabels, type SceneLabel, type ProjectedLabel } from "./SceneLabels";
import { GuidePlayer } from "./GuidePlayer";
import { ExploreCamera } from "./ExploreCamera";
import { Pictogram } from "./Pictogram";
import { PickIntent } from "../lib/interaction";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { advancePreview, routeRuns, presentation, samplePreview, type Presentation } from "../lib/playback";
import { openingFrame } from "../lib/openings";
import { bounds } from "../lib/geometry";
import { kindOf, kindScene } from "../lib/roomKinds";
import type { Asset, Geometry, Opening, Route, Space, VisualResult, XY } from "../lib/types";

const COLORS: Record<string,string> = {circulation:"#647a83", hall:"#586b70", office:"#82969b", lab:"#668e89", service:"#7b7d8c", core:"#435c66"};
const frame = (x:number,y:number,h:number) => new THREE.Vector3(x,h,-y);
/** Distance from a point to the nearest edge of a polygon. */
function edgeDistance(poly:XY[],px:number,py:number){return poly.reduce((m,q,i)=>{const r=poly[(i+1)%poly.length],dx=r[0]-q[0],dy=r[1]-q[1],l2=dx*dx+dy*dy||1,t=Math.max(0,Math.min(1,((px-q[0])*dx+(py-q[1])*dy)/l2));return Math.min(m,Math.hypot(px-q[0]-t*dx,py-q[1]-t*dy));},Infinity);}
/** Move a point toward the polygon's centre until it is inside and at least `margin` metres from every edge (or as far as it gets in 24 steps). */
function pullInside(poly:XY[],x:number,y:number,margin:number):[number,number]{
  // Aim for the roomiest point of the polygon (the spot farthest from every wall), not its centroid: an L-shaped or skewed hall has a centroid beside a wall.
  const xs=poly.map(q=>q[0]),ys=poly.map(q=>q[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  let cx=poly.reduce((a,q)=>a+q[0],0)/poly.length,cy=poly.reduce((a,q)=>a+q[1],0)/poly.length,best=insidePolygon(poly,cx,cy)?edgeDistance(poly,cx,cy):-1;
  for(let i=0;i<=12;i++)for(let j=0;j<=12;j++){const gx=x0+(x1-x0)*i/12,gy=y0+(y1-y0)*j/12;if(!insidePolygon(poly,gx,gy))continue;const d=edgeDistance(poly,gx,gy);if(d>best){best=d;cx=gx;cy=gy;}}
  let px=x,py=y;
  for(let k=0;k<24&&(!insidePolygon(poly,px,py)||edgeDistance(poly,px,py)<margin);k++){px+=(cx-px)*.15;py+=(cy-py)*.15;}
  return [px,py];
}
type Plates=Record<string,{exterior:XY[];holes:XY[][]}[]>|undefined;
/** The floor plate of one space. Where a stair flight arrives, the scene supplies the plate with the flight's footprint cut out, so
 *  no floor stands inside a staircase; every other space is its plain polygon. */
function floorShape(space: Space, plates?: Plates) {
  const pieces=plates?.[space.id]??[{exterior:space.polygon,holes:[]}];
  const parts=pieces.map(piece=>{
    const shape=new THREE.Shape();
    piece.exterior.forEach(([x,y],i) => i ? shape.lineTo(x,y) : shape.moveTo(x,y));
    for(const ring of piece.holes){const hole=new THREE.Path();ring.forEach(([x,y],i)=>i?hole.lineTo(x,y):hole.moveTo(x,y));shape.holes.push(hole);}
    const g=new THREE.ShapeGeometry(shape);g.rotateX(-Math.PI/2);return g.toNonIndexed();
  });
  if(parts.length===1)return parts[0];
  const merged=mergeGeometries(parts);parts.forEach(p=>p.dispose());return merged;
}

const ZONE_COLORS:Record<string,string>={hazard:"#e5484d",responder:"#3b82c4",crowd1:"#b99a3c",crowd2:"#f2b705",highlight:"#ffd45c"};

/** Density heat map from the evacuation test: space id to a hex colour; read by every floor so it needs no prop drilling. */
const HeatContext=createContext<Record<string,string>|undefined>(undefined);
function Floors({spaces,elevation,highlights,hazard,zones,onPick,plates,overlaps}:{plates?:Plates;overlaps?:NonNullable<Geometry["scene"]>["overlaps"];spaces:Space[];elevation:number;highlights:Set<string>;hazard?:string;zones?:Record<string,string>;onPick?:(s:Space)=>void}) {
  const heat=useContext(HeatContext);
  const batches = useMemo(() => {
    const groups = new Map<string,Space[]>();
    spaces.forEach(s => {const key=heat?.[s.id]??(s.id===hazard?"hazard":zones?.[s.id]==="responder"?"responder":highlights.has(s.id)?"highlight":zones?.[s.id]??kindOf(s)); groups.set(key,[...(groups.get(key)??[]),s]);});
    return [...groups].map(([zone,rooms]) => {
      let triangles=0;
      const ranges:{end:number;space:Space}[]=[];
      const pieces=rooms.map(s=>{const g=floorShape(s,plates);triangles+=g.getAttribute("position").count/3;ranges.push({end:triangles,space:s});return g;});
      const geometry=mergeGeometries(pieces); pieces.forEach(p=>p.dispose());
      return {zone,geometry,ranges};
    });
  },[spaces,highlights,hazard,zones,plates,heat]);
  useEffect(()=>()=>batches.forEach(b=>b.geometry?.dispose()),[batches]);
  /** Where two rooms overlap in the data, the shared part is drawn once as the mix of both room colours (no flicker, nothing hidden). */
  const blends=useMemo(()=>{
    const byId=new Map(spaces.map(s=>[s.id,s]));
    return (overlaps??[]).filter(o=>byId.has(o.a)&&byId.has(o.b)).map(o=>{
      const shape=new THREE.Shape();o.polygon.forEach(([x,y],i)=>i?shape.lineTo(x,y):shape.moveTo(x,y));
      const g=new THREE.ShapeGeometry(shape);g.rotateX(-Math.PI/2);
      return {key:`${o.a}|${o.b}|${o.polygon[0]?.join(",")}`,geometry:g,color:new THREE.Color(kindScene(byId.get(o.a)!)).lerp(new THREE.Color(kindScene(byId.get(o.b)!)),.5)};
    });
  },[spaces,overlaps]);
  useEffect(()=>()=>blends.forEach(b=>b.geometry.dispose()),[blends]);
  return <group position={[0,elevation,0]}>{blends.map(b=><mesh key={b.key} geometry={b.geometry} raycast={()=>null} renderOrder={1}>
    <meshStandardMaterial color={b.color} roughness={0.94} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-60}/></mesh>)}{batches.map((b,index)=>b.geometry&&<mesh key={b.zone} geometry={b.geometry} receiveShadow
    onAfterRender={renderer=>{renderer.domElement.dataset.scenePainted="true";}}
    onClick={(e:ThreeEvent<MouseEvent>)=>{e.stopPropagation();if(e.delta>5)return;const room=b.ranges.find(r=>(e.faceIndex??0)<r.end);if(room)onPick?.(room.space);}}>
    <meshStandardMaterial color={b.zone.startsWith("#")?b.zone:ZONE_COLORS[b.zone]??kindScene(b.ranges[0].space)} roughness={0.94} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-index-1}/>
  </mesh>)}</group>;
}

function doorsOf(geometry:Geometry):Door[]{
  return geometry.openings.filter(o=>["door","opening","entrance"].includes(o.kind)).flatMap(o=>{
    const f=openingFrame(geometry,o);if(!f)return [];
    return [{ids:o.space_ids,x:o.position[0],y:o.position[1],nx:-Math.sin(f.angle),ny:Math.cos(f.angle)}];
  });
}

function GhostFloors({spaces,elevation}:{spaces:Space[];elevation:number}) {
  const geometry=useMemo(()=>{
    const pieces=spaces.map(s=>floorShape(s).toNonIndexed());
    if(!pieces.length)return null;
    const g=mergeGeometries(pieces);pieces.forEach(p=>p.dispose());return g;
  },[spaces]);
  useEffect(()=>()=>geometry?.dispose(),[geometry]);
  if(!geometry)return null;
  return <mesh geometry={geometry} position={[0,elevation+.012,0]} renderOrder={0}><meshBasicMaterial color="#2c3f49" transparent opacity={.55} depthWrite={false} side={THREE.DoubleSide}/></mesh>;
}

function Walls({geometry,floorId,elevation,follow,relevant}:{geometry:Geometry;floorId:string;elevation:number;follow:boolean;relevant?:Set<string>|null}) {
  const mesh=useMemo(()=>{
    const pos:number[]=[];
    const walls=geometry.scene?.walls.filter(w=>w.floor_id===floorId&&(!relevant||(w.space_id!=null&&relevant.has(w.space_id))))??[];
    const seen=new Set<string>(),key=(p:number[])=>`${Math.round(p[0]*50)},${Math.round(p[1]*50)}`;
    for(const w of walls){
      const k1=key(w.a),k2=key(w.b),k=k1<k2?k1+"|"+k2:k2+"|"+k1;if(seen.has(k))continue;seen.add(k);
      const [x,z]=[w.a[0],-w.a[1]], [u,v]=[w.b[0],-w.b[1]];
      // Cutaway heights in overview; supplied heights in the eye-level view.
      const h=follow?w.height_m:Math.min(w.height_m,1.35);
      pos.push(x,0,z,u,0,v,u,h,v,x,0,z,u,h,v,x,h,z);
    }
    // Lintels: the wall above doors and narrow openings, so doorways are holes in a wall and not gaps to the sky.
    if(follow)for(const w of geometry.scene?.headers?.filter(h=>h.floor_id===floorId&&!relevant)??[]){
      const [x,z]=[w.a[0],-w.a[1]], [u,v]=[w.b[0],-w.b[1]],b=w.base_m,h=w.height_m;
      pos.push(x,b,z,u,b,v,u,h,v,x,b,z,u,h,v,x,h,z);
    }
    const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.Float32BufferAttribute(pos,3));g.computeVertexNormals();return g;
  },[geometry.scene?.revision,floorId,follow,relevant]);
  const edges=useMemo(()=>new THREE.EdgesGeometry(mesh,30),[mesh]);
  const tint=floorColor(geometry.floors.find(f=>f.id===floorId)?.level??0);
  useEffect(()=>()=>{mesh.dispose();edges.dispose();},[mesh,edges]);
  return <group position={[0,elevation,0]}><mesh geometry={mesh} castShadow receiveShadow userData={{labelOccluder:true}}><meshStandardMaterial color="#93a6ad" roughness={0.78} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}/></mesh>
    <lineSegments geometry={edges}><lineBasicMaterial color={tint} transparent opacity={follow?0.18:0.55}/></lineSegments></group>;
}

function Doorways({geometry,floorId,elevation,follow,activeOpening,relevant}:{geometry:Geometry;floorId:string;elevation:number;follow:boolean;activeOpening?:string;relevant?:Set<string>|null}) {
  const ref=useRef<THREE.InstancedMesh>(null);
  const parts=useMemo(()=>geometry.openings.filter(o=>o.floor_id===floorId&&(!relevant||o.space_ids.some(id=>relevant.has(id)))&&Number.isFinite(o.width_m)&&o.width_m>0&&["door","entrance","opening"].includes(o.kind)).flatMap(o=>{
    const alignment=openingFrame(geometry,o);if(!alignment)return [];
    const height=follow?Math.min(2.1,(geometry.floors.find(f=>f.id===floorId)?.height_m??3)-.1):1.25;
    const width=Math.max(.1,o.width_m),color=o.id===activeOpening?"#ffd45c":o.kind==="entrance"?"#66bea0":o.kind==="opening"?"#8cabb7":"#bba786";
    const base={alignment,color};
    const parts=[{...base,x:0,y:.012,w:width,h:.025,d:.22}];
    const stairOpen=o.space_ids.some(id=>geometry.spaces.find(sp=>sp.id===id)?.type==="stair"||geometry.spaces.find(sp=>sp.id===id)?.type==="lift");
    if(o.kind!=="opening"&&!stairOpen)parts.push(...[-1,1].map(sign=>({...base,x:sign*(width/2+.025),y:height/2,w:.055,h:height,d:.12})),{...base,x:0,y:height,w:width+.1,h:.07,d:.12});
    return parts;
  }),[geometry,floorId,follow,activeOpening,relevant]);
  useEffect(()=>{if(!ref.current)return;const parent=new THREE.Object3D(),part=new THREE.Object3D();parts.forEach((p,i)=>{
    parent.position.set(p.alignment.x,0,-p.alignment.y);parent.rotation.y=p.alignment.angle;parent.updateMatrix();
    part.position.set(p.x,p.y,0);part.scale.set(p.w,p.h,p.d);part.updateMatrix();
    ref.current!.setMatrixAt(i,parent.matrix.clone().multiply(part.matrix));ref.current!.setColorAt(i,new THREE.Color(p.color));
  });ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;ref.current.computeBoundingSphere();},[parts]);
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}><boxGeometry/><meshStandardMaterial roughness={.7} metalness={.15}/></instancedMesh></group>;
}

const FloorScene=memo(function FloorScene({geometry,floorId,elevation,highlights,onSpaceClick,follow,ceiling,span,hazard,zones,connectorSpaces,labelFloor,activeOpening,relevant,voids,bare,near}:{near:boolean;hazard?:string;zones?:Record<string,string>;bare?:boolean;relevant?:Set<string>|null;voids:Set<string>;geometry:Geometry;floorId:string;elevation:number;highlights:Set<string>;onSpaceClick?:(s:Space)=>void;follow:boolean;ceiling:boolean;span:number;connectorSpaces:Set<string>;labelFloor:string;activeOpening?:string}) {
  const spaces=useMemo(()=>geometry.spaces.filter(s=>s.floor_id===floorId&&!voids.has(s.id)&&(!relevant||relevant.has(s.id))),[geometry,floorId,relevant,voids]);
  const assets=useMemo(()=>bare?[]:geometry.assets.filter(a=>a.floor_id===floorId&&(!relevant||relevant.has(a.space_id))),[geometry,floorId,relevant,bare]);
  const rings=useMemo(()=>new Map(geometry.spaces.filter(s=>s.floor_id===floorId).map(s=>[s.id,s.polygon as [number,number][]])),[geometry,floorId]);
  const hidden=useMemo(()=>relevant?geometry.spaces.filter(s=>s.floor_id===floorId&&!voids.has(s.id)&&!relevant.has(s.id)):[],[geometry,floorId,relevant,voids]);
  const height=geometry.floors.find(f=>f.id===floorId)?.height_m??3;
  const roomHighlights=highlights;
  return <group>
        <Floors spaces={spaces} elevation={elevation} highlights={roomHighlights} hazard={hazard} zones={zones} onPick={onSpaceClick} plates={geometry.scene?.plates} overlaps={geometry.scene?.overlaps}/>
        {hidden.length>0&&<GhostFloors spaces={hidden} elevation={elevation}/>}
        <Walls geometry={geometry} floorId={floorId} elevation={elevation} follow={follow} relevant={relevant}/>
        <Doorways geometry={geometry} floorId={floorId} elevation={elevation} follow={follow} activeOpening={activeOpening} relevant={relevant}/>

        <SceneAssets interior={follow} near={near} context={assets} rings={rings} assets={assets.filter(a=>!highlights.has(a.id))} elevation={elevation} highlighted={false}/>
        <SceneAssets interior={follow} near={near} context={assets} rings={rings} assets={assets.filter(a=>highlights.has(a.id))} elevation={elevation} highlighted/>
  </group>;
});

function Path({route,geometry,explode=0,ghost=false,xray=false,visibleFloors,casing=1}:{route:Route;geometry:Geometry;explode?:number;ghost?:boolean;xray?:boolean;visibleFloors:Set<string>;casing?:number}){
  const meshes=useMemo(()=>routeRuns(route,visibleFloors).map(run=>{
    const points=run.map(p=>{const f=geometry.floors.find(f=>f.id===p.floor_id);return frame(p.x,p.y,(f?.elevation_m??0)+(f?.level??0)*explode+(ghost?.03:.075)-(casing>1?.01:0));});
    const vertices:number[]=[],radius=(ghost?.055:.125)*casing;
    for(let i=1;i<points.length;i++){
      const a=points[i-1],b=points[i],delta=b.clone().sub(a);if(delta.length()<1e-6)continue;
      const n=new THREE.Vector3(-delta.z,0,delta.x).normalize().multiplyScalar(radius);
      const l=a.clone().add(n),r=a.clone().sub(n),u=b.clone().add(n),v=b.clone().sub(n);
      for(const p of [l,r,u,r,v,u])vertices.push(p.x,p.y,p.z);
    }
    for(const p of points)for(let k=0;k<12;k++)for(const v of [p,new THREE.Vector3(p.x+radius*Math.cos(k*Math.PI/6),p.y,p.z+radius*Math.sin(k*Math.PI/6)),new THREE.Vector3(p.x+radius*Math.cos((k+1)*Math.PI/6),p.y,p.z+radius*Math.sin((k+1)*Math.PI/6))])vertices.push(v.x,v.y,v.z);
    const mesh=new THREE.BufferGeometry();mesh.setAttribute("position",new THREE.Float32BufferAttribute(vertices,3));mesh.computeVertexNormals();return mesh;
  }),[route,geometry,explode,visibleFloors,ghost,casing]);
  useEffect(()=>()=>meshes.forEach(m=>m.dispose()),[meshes]);
  return <>{meshes.map((g,i)=><mesh key={i} geometry={g} renderOrder={ghost?1:xray?3:casing>1?1:2}><meshBasicMaterial color={ghost?"#869ba5":casing>1?"#3b2d05":"#ffd45c"} side={THREE.DoubleSide} transparent={ghost||xray} opacity={ghost?.3:xray?.3:1} depthTest={!xray} depthWrite={false} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-2}/></mesh>)}</>;
}


function RouteCamera({geometry,model,clock,playing,speed,seekVersion,onSample,lookOffset}:{geometry:Geometry;model:Presentation;clock:MutableRefObject<number>;playing:boolean;speed:number;seekVersion:number;onSample:(time:number)=>void;lookOffset?:{yaw:number;pitch:number}}){
  const {camera,invalidate,gl,scene}=useThree();const sight=useMemo(()=>new THREE.Raycaster(),[]);const lastReport=useRef(-1);const first=useRef(true);const heading=useRef<THREE.Vector3|null>(null);const walkCache=useRef(new Map<string,WalkPoint[]|null>());const lastTick=useRef(performance.now());
  useLayoutEffect(()=>{lastTick.current=performance.now();},[playing]);
  // The Canvas reads its camera props once at creation (overview: near ~0.6 m, fov 40). The walking camera needs its own lens, and the
  // overview lens must come back afterwards: otherwise everything within the overview near plane is clipped away.
  useLayoutEffect(()=>{
    const cam=camera as THREE.PerspectiveCamera,saved={near:cam.near,fov:cam.fov,far:cam.far};
    cam.near=0.05;cam.fov=70;cam.far=Math.max(120,Math.min(saved.far,400));cam.updateProjectionMatrix();invalidate();
    return()=>{cam.near=saved.near;cam.fov=saved.fov;cam.far=saved.far;cam.updateProjectionMatrix();invalidate();};
  },[camera,invalidate]);
  useEffect(()=>{first.current=true;invalidate();},[seekVersion,model,invalidate]);
  useEffect(()=>{invalidate();},[lookOffset,invalidate]);
  // Look around by dragging, in the walk and especially at the destination once the preview has finished. Playing again straightens the view.
  const drag=useRef({yaw:0,pitch:0});
  useEffect(()=>{if(playing)drag.current={yaw:0,pitch:0};},[playing,seekVersion]);
  useEffect(()=>{
    const el=gl.domElement;let down=false,lx=0,ly=0;
    const onDown=(e:PointerEvent)=>{down=true;lx=e.clientX;ly=e.clientY;el.setPointerCapture?.(e.pointerId);el.style.cursor="grabbing";};
    const onMove=(e:PointerEvent)=>{if(!down)return;drag.current.yaw-=(e.clientX-lx)*.25;drag.current.pitch=Math.max(-70,Math.min(70,drag.current.pitch+(e.clientY-ly)*.2));lx=e.clientX;ly=e.clientY;invalidate();};
    const onUp=(e:PointerEvent)=>{down=false;el.releasePointerCapture?.(e.pointerId);el.style.cursor="grab";};
    el.style.cursor="grab";
    el.addEventListener("pointerdown",onDown);el.addEventListener("pointermove",onMove);el.addEventListener("pointerup",onUp);el.addEventListener("pointercancel",onUp);
    return()=>{el.removeEventListener("pointerdown",onDown);el.removeEventListener("pointermove",onMove);el.removeEventListener("pointerup",onUp);el.removeEventListener("pointercancel",onUp);el.style.cursor="";};
  },[gl,invalidate]);
  useFrame((_,dt)=>{
    const now=performance.now(),elapsed=Math.max(0,(now-lastTick.current)/1000);lastTick.current=now;
    if(playing)clock.current=advancePreview(clock.current,elapsed,speed,model.duration);
    const sample=samplePreview(model,clock.current),p=sample.point;if(!p)return;
    const height=geometry.floors.find(f=>f.id===p.floor_id)?.elevation_m??0;
    const ride=sample.ride;let rideDelta=0;let rideTan:THREE.Vector3|null=null;
    if(ride){
      // Ride the connector: glide between the two landings instead of cutting between floors.
      const e=ease(ride.t),h0=geometry.floors.find(f=>f.id===ride.from.floor_id)?.elevation_m??0,h1=geometry.floors.find(f=>f.id===ride.to.floor_id)?.elevation_m??0;
      rideDelta=h1-h0;
      // Stay inside the stair or lift shaft while climbing: pull each position toward the shaft centre until it is inside its outline.
      const shaft=[ride.from.node,ride.to.node].map(id=>geometry.spaces.find(sp=>sp.id===id)?.polygon).filter((q):q is XY[]=>!!q&&q.length>2);
      const key=`${ride.from.floor_id}|${ride.to.floor_id}|${ride.from.node}|${ride.to.node}`;
      if(!walkCache.current.has(key))walkCache.current.set(key,stairWalkFor(geometry,ride.from.floor_id,ride.to.floor_id,ride.from.node,ride.to.node));
      let line=walkCache.current.get(key);
      if(line&&h1<h0)line=[...line].reverse();
      // Start the walk where the person really enters the stair space and end where the route continues upstairs: the flight line alone starts
      // 0.4 m before the first tread, which showed as a sideways hop at the door.
      if(line){
        // keep both ends 0.45 m inside the stair space: the route's own points can lie on the shaft wall
        const fromPoly=geometry.spaces.find(sp=>sp.id===ride.from.node)?.polygon,toPoly=geometry.spaces.find(sp=>sp.id===ride.to.node)?.polygon;
        const [fx,fy]=fromPoly?pullInside(fromPoly,ride.from.x,ride.from.y,.45):[ride.from.x,ride.from.y];
        const [tx,ty]=toPoly?pullInside(toPoly,ride.to.x,ride.to.y,.45):[ride.to.x,ride.to.y];
        line=[{x:fx,y:fy,h:h0+.02},...line,{x:tx,y:ty,h:h1+.02}];
      }
      let rx=ride.from.x+(ride.to.x-ride.from.x)*e,ry=ride.from.y+(ride.to.y-ride.from.y)*e,rh=h0+(h1-h0)*e;
      if(line){ // walk the real flights: position, height and heading come from the stair's own line
        const len=line.slice(1).reduce((a,q,i)=>a+Math.hypot(q.x-line![i].x,q.y-line![i].y),0);let want=len*e,acc=0,k=0;
        while(k<line.length-2&&acc+Math.hypot(line[k+1].x-line[k].x,line[k+1].y-line[k].y)<want){acc+=Math.hypot(line[k+1].x-line[k].x,line[k+1].y-line[k].y);k++;}
        const a=line[k],b=line[k+1],seg=Math.hypot(b.x-a.x,b.y-a.y)||1,u=Math.max(0,Math.min(1,(want-acc)/seg));
        rx=a.x+(b.x-a.x)*u;ry=a.y+(b.y-a.y)*u;rh=a.h+(b.h-a.h)*u;rideTan=new THREE.Vector3(b.x-a.x,0,-(b.y-a.y));
      }
      if(shaft.length){ // never closer than the camera radius to the stair's walls (the flight line can graze a skewed shaft)
        const home=shaft.find(q=>insidePolygon(q,rx,ry))??shaft[e<.5?0:shaft.length-1];
        [rx,ry]=pullInside(home,rx,ry,.47);
      }
      if(vrPose.active){vrPose.x=rx;vrPose.y=rh;vrPose.z=-ry;}else camera.position.copy(frame(rx,ry,rh+1.65));
      const lift=geometry.connectors.some(c=>c.kind==="lift"&&c.space_ids.includes(ride.from.node)&&c.space_ids.includes(ride.to.node));
      rideState.lift=lift?{nodes:[ride.from.node,ride.to.node],y:h0+(h1-h0)*e+.02}:null;
    }else{
      rideState.lift=null;
      // The camera path is already centred and clear of walls; nothing is pushed per frame (that made the picture jitter).
      if(vrPose.active){vrPose.x=p.x;vrPose.y=height;vrPose.z=-p.y;}else camera.position.copy(frame(p.x,p.y,height+1.65));
    }
    // Look along the camera path: the average direction to where we will be 1 to 2.6 s from now, low-passed, so corners turn smoothly.
    const target=new THREE.Vector3();
    if(!sample.transition){
      for(const seconds of [1.2,2.2,3.2]){
        const ahead=samplePreview(model,Math.min(model.duration,clock.current+seconds));
        if(ahead.transition||ahead.point?.floor_id!==p.floor_id)continue;
        target.add(new THREE.Vector3(ahead.point.x-p.x,0,-(ahead.point.y-p.y)).normalize());
      }
    }
    if(target.lengthSq()<1e-6)target.set(sample.heading[0],0,-sample.heading[1]);
    if(rideTan&&rideTan.lengthSq()>1e-8)target.copy(rideTan);
    target.y=0;if(target.lengthSq()<1e-6)target.set(0,0,-1);target.normalize();
    if(first.current||!heading.current)heading.current=target.clone();
    else{ // turn toward the target: eased, but never faster than 80 degrees per second
      const cross=heading.current.x*target.z-heading.current.z*target.x,dot=heading.current.dot(target),angle=Math.atan2(cross,dot);
      const step=Math.sign(angle)*Math.min(Math.abs(angle)*(1-Math.exp(-dt/0.45)),THREE.MathUtils.degToRad(80)*dt);
      heading.current.applyAxisAngle(new THREE.Vector3(0,-1,0),step).normalize();
    }
    if(vrPose.active){ // a headset owns the camera: move the VR rig along the path and keep reporting progress
      vrPose.yaw=Math.atan2(-heading.current.x,-heading.current.z);first.current=false;
      if(Math.abs(clock.current-lastReport.current)>.08||sample.arrived||!playing){lastReport.current=clock.current;onSample(clock.current);}
      if(playing)invalidate();
      return;
    }
    const direction=heading.current.clone();
    direction.y=-(rideDelta<0?.5:rideDelta>0?-.2:.14);
    const matrix=new THREE.Matrix4().lookAt(camera.position,camera.position.clone().add(direction),new THREE.Vector3(0,1,0));
    const aim=new THREE.Quaternion().setFromRotationMatrix(matrix);
    const yawOffset=(lookOffset?.yaw??0)+drag.current.yaw,pitchOffset=Math.max(-80,Math.min(80,(lookOffset?.pitch??0)+drag.current.pitch));
    if(yawOffset||pitchOffset)aim.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(pitchOffset),-THREE.MathUtils.degToRad(yawOffset),0,"YXZ")));
    camera.quaternion.copy(aim);
    if(heading.current.angleTo(target)>.01)invalidate();
    first.current=false;
    camera.updateProjectionMatrix();gl.domElement.dataset.cameraNear=String((camera as THREE.PerspectiveCamera).near);gl.domElement.dataset.cameraFov=String((camera as THREE.PerspectiveCamera).fov);gl.domElement.dataset.cameraPosition=JSON.stringify(camera.position.toArray());gl.domElement.dataset.cameraFloor=p.floor_id;gl.domElement.dataset.cameraQuaternion=JSON.stringify(camera.quaternion.toArray());
    if(Math.abs(clock.current-lastReport.current)>.08 || sample.arrived || !playing){lastReport.current=clock.current;onSample(clock.current);}
    if(playing)invalidate();
  });return null;
}

export function Building3D({geometry,floorId,route,previousRoute,highlights=new Set(),hazard,zones,closed=new Set(),previewDoor,showAll,scope="current",exploded=true,follow=false,previewMode=true,activeStep=0,seekRequest=0,onStep,onSpaceClick,onFinish,onPreview,here,selected,visualResult,onPosition,heading,onRepeat,focusRequest,lookOffset,focus:focusProp=true,onFocus,heat,pins}: {
  heat?:Record<string,string>;pins?:{id:string;floor_id:string;x:number;y:number}[];
 onFocus?:(v:boolean)=>void;
 focus?:boolean;
 hazard?:string;zones?:Record<string,string>;
 geometry:Geometry;floorId:string;route?:Route|null;previousRoute?:Route|null;highlights?:Set<string>;closed?:Set<string>;previewDoor?:Opening|null;
 lookOffset?:{yaw:number;pitch:number};focusRequest?:{id:string;revision:number}|null;onRepeat?:()=>void;heading?:number;visualResult?:VisualResult|null;onPosition?:(p:{x:number;y:number;floor_id:string;heading?:number})=>void;showAll:boolean;scope?:"current"|"route"|"building";exploded?:boolean;previewMode?:boolean;seekRequest?:number;onFinish?:()=>void;onPreview?:()=>void;here?:string|null;selected?:string|null;follow?:boolean;activeStep?:number;onStep?:(i:number)=>void;onSpaceClick?:(s:Space)=>void;
}){
  const autoSpeed=true; // Guide me always skips the uneventful stretches and slows at doors, turns and stairs: no switch to maintain
  const [infoOpen,setInfoOpen]=useState(false);
  const [detail,setDetail]=useState<Detail>({near:true,y:0});
  // Touch devices: no antialiasing and a lower pixel ratio ceiling; every device drops to 1x while frames are slow and recovers at rest.
  const coarse=typeof matchMedia!=="undefined"&&matchMedia("(pointer: coarse)").matches,maxDpr=coarse?1.25:1.5;
  const [dpr,setDpr]=useState(maxDpr);
  const [focusInner,setFocusInner]=useState(focusProp);
  const focus=onFocus?focusProp:focusInner;
  const setFocus=(f:(v:boolean)=>boolean)=>{const next=f(focus);if(onFocus)onFocus(next);else setFocusInner(next);};
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
  const clock=useRef(0), model=useMemo(()=>route?presentation(follow?{...route,polyline:cameraPath(route.polyline,geometry.scene?.walls??[],doorsOf(geometry))}:route,autoSpeed,(fa,fb,na,nb)=>{const l=stairWalkFor(geometry,fa,fb,na,nb);if(!l)return 3;return Math.max(3,l.slice(1).reduce((t,q,i)=>t+Math.hypot(q.x-l[i].x,q.y-l[i].y),0)/0.9);}):null,[route,follow,geometry,autoSpeed]);
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
  const report=(value:number)=>{setTime(old=>Math.abs(old-value)>.001?value:old);if(!model)return;const s=samplePreview(model,value);if(s.step!==activeStep)onStep?.(s.step);if(s.point)onPosition?.({...s.point,heading:(Math.atan2(s.heading[0],s.heading[1])*180/Math.PI+360)%360});if(s.arrived)setPlaying(false);};
  const box=useMemo(()=>bounds(geometry.spaces.flatMap(s=>s.polygon)),[geometry]);
  const fitBox=useMemo(()=>{
    const rooms=geometry.spaces.filter(s=>(scope!=="current"||visualResult?.kind==="stacking"||visualResult?.kind==="distance"||s.floor_id===floorId)&&(emphasis?s.id===emphasis:highlights.has(s.id)));
    const points=[...rooms.flatMap(s=>s.polygon),...geometry.assets.filter(a=>!emphasis&&(scope!=="current"||a.floor_id===floorId)&&highlights.has(a.id)).map(a=>a.position)];
    if(!points.length)return box;
    const b=bounds(points);
    const roomW=b.maxX-b.minX,roomH=b.maxY-b.minY;
    const pad=emphasis?Math.max(3,Math.max(roomW,roomH)*0.35):3;
    return {minX:b.minX-pad,maxX:b.maxX+pad,minY:b.minY-pad,maxY:b.maxY+pad};
  },[geometry,floorId,emphasis,highlights,box,scope,visualResult?.kind]);
  const cx=(box.minX+box.maxX)/2,cz=-(box.minY+box.maxY)/2,span=Math.max(box.maxX-box.minX,box.maxY-box.minY,10);
  const multi=!emphasis&&((visualResult?.kind==="stacking"||visualResult?.kind==="distance")||showAll||scope==="building"||(scope==="route"&&!!route))&&!follow;
  const explode=multi&&exploded&&visualResult?.kind!=="distance"?2:0;
  const elevation=(id:string)=>{const f=geometry.floors.find(f=>f.id===id);return (f?.elevation_m??0)+(f?.level??0)*explode;};
  const activeFloor=follow?(sample?.point?.floor_id??floorId):floorId;
  const floors=geometry.floors.filter(f=>(visualResult?.kind==="stacking"||visualResult?.kind==="distance")&&!follow?visualResult.floor_ids.includes(f.id):multi?((scope==="route"||(scope==="building"&&focus&&!!route&&!showAll))?route?.floors.includes(f.id):true):(follow||f.id===activeFloor));
  const visibleFloors=useMemo(()=>new Set(floors.map(f=>f.id)),[floors.map(f=>f.id).join()]);
  const elevations=useMemo(()=>Object.fromEntries(geometry.floors.map(f=>[f.id,(f.elevation_m??0)+(f.level??0)*explode])),[geometry,explode]);
  const usedConnectors=useMemo(()=>{
    const used=new Set<string>(),nodes=route?.polyline.map(p=>p.node)??[];
    nodes.forEach((node,i)=>{const next=nodes[i+1];if(!next||next===node)return;
      for(const c of geometry.connectors)if(c.space_ids.includes(node)&&c.space_ids.includes(next))used.add(c.id);});
    return used;
  },[geometry,route]);
  const roomHighlights=useMemo(()=>new Set([...highlights,...(selected?[selected]:[])]),[highlights,selected]);
  const relevant=useMemo(()=>focus&&(scope!=="building"||!!route)&&!visualResult?relevantSpaces(geometry,route,[...highlights,...(selected?[selected]:[]),...(here?[here]:[])]):null,[focus,follow,scope,route,highlights,selected,here,geometry,visualResult]);
  const voids=useMemo(()=>shaftVoids(geometry),[geometry]);
  const hiddenCount=useMemo(()=>relevant?geometry.spaces.filter(sp=>visibleFloors.has(sp.floor_id)&&!voids.has(sp.id)&&!relevant.has(sp.id)).length:0,[relevant,geometry,visibleFloors,voids]);
  // With focus on, frame the rooms that are drawn instead of the whole building.
  const focusBox=useMemo(()=>{
    if(!relevant)return null;
    const pts=geometry.spaces.filter(sp=>relevant.has(sp.id)&&(scope!=="current"||sp.floor_id===floorId)).flatMap(sp=>sp.polygon);
    if(!pts.length)return null;const b=bounds(pts),pad=4;return {minX:b.minX-pad,maxX:b.maxX+pad,minY:b.minY-pad,maxY:b.maxY+pad};
  },[relevant,geometry,scope,floorId]);
  const connectorGeometry=useMemo(()=>relevant?{...geometry,connectors:geometry.connectors.filter(c=>c.space_ids.some(id=>relevant.has(id)))}:geometry,[geometry,relevant]);
  const [projectedLabels,setProjectedLabels]=useState<ProjectedLabel[]>([]);
  const sceneLabels=useMemo<SceneLabel[]>(()=>follow?[]:[
    ...geometry.connectors.flatMap(c=>c.space_ids.flatMap(id=>{const s=geometry.spaces.find(s=>s.id===id&&s.floor_id===floorId);if(!s||!visibleFloors.has(s.floor_id)||!connectorSpaces.has(id))return [];const b=bounds(s.polygon);return [{id:`connector-${id}`,text:c.name,icon:c.kind,position:[(b.minX+b.maxX)/2,elevation(s.floor_id)+.7,-(b.minY+b.maxY)/2] as [number,number,number]}];})),
    ...geometry.spaces.filter(s=>visibleFloors.has(s.floor_id)&&(s.id===emphasis||(highlights.size<=4&&highlights.has(s.id)))).map(s=>{const p=s.anchor??s.polygon[0];return {id:`room-${s.id}`,text:s.name,position:[p[0],elevation(s.floor_id)+1.7,-p[1]] as [number,number,number]};}),
    ...(visualResult?.kind==="intervention"?(()=>{const o=visualResult.measurements.proposed_opening as Opening|undefined;return o&&visibleFloors.has(o.floor_id)?[{id:"proposed",text:"Proposed opening · not applied",position:[o.position[0],elevation(o.floor_id)+1.8,-o.position[1]] as [number,number,number]}]:[];})():[])
  ],[geometry,follow,floorId,visibleFloors,connectorSpaces,emphasis,highlights,visualResult,explode]);
  /** Found items and highlighted rooms get a pulsing beacon (at most 12, so a "show all chairs" answer stays readable). */
  const beaconPoints=useMemo(()=>{
    if(follow||(!highlights.size&&!pins?.length))return [] as BeaconPoint[];
    const out:BeaconPoint[]=[];
    if(highlights.size)for(const a of geometry.assets){if(out.length>=12)break;if(highlights.has(a.id)&&visibleFloors.has(a.floor_id))out.push({id:a.id,x:a.position[0],y:elevation(a.floor_id)+.05,z:-a.position[1]});}
    if(out.length<12)for(const s of geometry.spaces){if(out.length>=12)break;if(highlights.has(s.id)&&visibleFloors.has(s.floor_id)){const p=s.anchor??s.polygon[0];out.push({id:s.id,x:p[0],y:elevation(s.floor_id)+.05,z:-p[1]});}}
    for(const p of pins??[])if(visibleFloors.has(p.floor_id))out.push({id:`pin-${p.id}`,x:p.x,y:elevation(p.floor_id)+.05,z:-p.y,color:"#ff5a5f"});
    return out;
  },[geometry,follow,highlights,visibleFloors,explode,pins]);

  return <div ref={stageRef} className="building-stage" onPointerDownCapture={e=>gesture.current.begin(e.clientX,e.clientY)} onPointerMoveCapture={e=>gesture.current.move(e.clientX,e.clientY)} onPointerCancelCapture={()=>gesture.current.cancel()} data-testid="building-scene" data-scene-revision={geometry.scene?.revision} data-ceiling-source="upper-floor-footprints" data-context-floors={follow?geometry.floors.filter(f=>f.elevation_m>elevation(activeFloor)+.05).map(f=>f.id).join(","):""} data-visible-floors={[...visibleFloors].join(",")} data-focus={relevant?"route":"all"} data-playback-state={sample?.arrived?"arrived":sample?.transition?"transition":playing?"playing":time?"paused":"idle"}>
    <Canvas frameloop={playing&&previewMode&&!reduced?"always":"demand"} dpr={[1,dpr]} camera={{position:[cx+span*.65,span*.8,cz+span*.8],fov:follow?70:40,near:follow?.05:Math.max(.5,span*.012),far:follow?Math.max(120,Math.min(span*3,400)):Math.max(200,span*6)}} shadows gl={{antialias:!coarse,logarithmicDepthBuffer:true,powerPreference:"high-performance"}}
      onCreated={({gl})=>{gl.setClearColor("#10171c");}}>
      <XR store={xrStore}>
      <SceneLighting cx={cx} cz={cz} span={span} interior={follow}/>
      <PerfProbe/>
      <PerformanceMonitor onDecline={()=>setDpr(1)} onIncline={()=>setDpr(maxDpr)} flipflops={3} onFallback={()=>setDpr(1)}/>
      {!follow&&<DetailWatcher span={span} onChange={setDetail}/>}
      {follow&&<Roofs geometry={geometry}/>}
      <HeatContext.Provider value={heat}>{floors.map(f=><FloorScene key={f.id} geometry={geometry} floorId={f.id} elevation={elevation(f.id)} highlights={roomHighlights} hazard={hazard} zones={zones} onSpaceClick={pick} follow={follow} ceiling={ceiling} span={span} connectorSpaces={connectorSpaces} labelFloor={floorId} activeOpening={activeOpening} relevant={relevant} voids={voids} bare={follow&&f.id!==activeFloor} near={detail.near&&(Math.abs(elevation(f.id)-detail.y)<=4.5||span<60)}/>)}</HeatContext.Provider>
      <Connectors3D geometry={connectorGeometry} elevations={elevations} visibleFloors={visibleFloors} activeFloor={activeFloor} used={usedConnectors}/>
      <LiftShafts geometry={connectorGeometry} elevations={elevations} visibleFloors={visibleFloors} activeFloor={activeFloor} used={usedConnectors}/>
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
      {!follow&&beaconPoints.length>0&&<Beacons points={beaconPoints}/>}
      {previousRoute&&!follow&&<Path route={previousRoute} geometry={geometry} explode={explode} visibleFloors={visibleFloors} ghost/>}
      {route&&<Path route={route} geometry={geometry} explode={explode} visibleFloors={visibleFloors} casing={1.7}/>}
      {route&&<Path route={route} geometry={geometry} explode={explode} visibleFloors={visibleFloors} xray={false}/>}
      {route&&!follow&&<Path route={route} geometry={geometry} explode={explode} visibleFloors={visibleFloors} xray/>}
      {route?.guide.steps.slice(activeStep+1,activeStep+2).map((s,i)=>s.point&&s.floor_id&&visibleFloors.has(s.floor_id)&&<mesh key={i} position={[s.point[0],elevation(s.floor_id)+0.15,-s.point[1]]}>
        <cylinderGeometry args={[0.38,0.38,0.1,24]}/><meshStandardMaterial color="#ffd45c" emissive="#a66c00" emissiveIntensity={0.5}/></mesh>)}
      {geometry.openings.filter(o=>visibleFloors.has(o.floor_id)&&(closed.has(o.id)||previewDoor?.id===o.id)).map(o=><mesh key={o.id} position={[o.position[0],elevation(o.floor_id)+.6,-o.position[1]]}>
        <boxGeometry args={[Math.max(o.width_m,.3),1.2,.15]}/><meshStandardMaterial color={closed.has(o.id)?"#ff8a8f":"#ffd45c"} emissive={closed.has(o.id)?"#9c202c":"#7c5612"}/></mesh>)}
      {geometry.connectors.filter(c=>closed.has(c.id)).flatMap(c=>c.space_ids.map(id=>geometry.spaces.find(s=>s.id===id)).filter((s):s is Space=>!!s&&visibleFloors.has(s.floor_id))).map(s=>{
        const r=orientedRect(s.polygon);return <mesh key={s.id} position={[r.cx,elevation(s.floor_id)+.7,-r.cy]} rotation={[0,Math.atan2(r.uy,r.ux),0]}><boxGeometry args={[Math.max(r.length-.1,.5),1.4,Math.max(r.width-.1,.5)]}/><meshStandardMaterial color="#ff8a8f" transparent opacity={.5} depthWrite={false}/></mesh>;
      })}
      {here&&geometry.spaces.filter(s=>s.id===here&&visibleFloors.has(s.floor_id)).map(s=>{const point=route?.stops[0]===here?route.polyline[0]:null;const b=bounds(s.polygon);return <group key={s.id} position={[point?.x??s.anchor?.[0]??(b.minX+b.maxX)/2,elevation(s.floor_id)+.08,-(point?.y??s.anchor?.[1]??(b.minY+b.maxY)/2)]}><mesh rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.14,.22,24]}/><meshBasicMaterial color="#65d7ac" side={THREE.DoubleSide} depthTest={false}/></mesh><mesh position={[0,.12,0]}><sphereGeometry args={[.1,12,8]}/><meshStandardMaterial color="#65d7ac" emissive="#1e7a4c"/></mesh>{heading!==undefined&&<group rotation={[0,-heading*Math.PI/180,0]}><mesh position={[0,.15,-.65]} rotation={[-Math.PI/2,0,0]}><coneGeometry args={[.2,.5,3]}/><meshBasicMaterial color="#65d7ac"/></mesh></group>}</group>;})}
      {follow&&route&&model?<RouteCamera geometry={geometry} model={model} clock={clock} playing={playing&&previewMode&&!reduced} speed={speed} seekVersion={seekVersion} onSample={report} lookOffset={lookOffset}/>
        :<><OrbitControls mouseButtons={{LEFT:orbiting?THREE.MOUSE.ROTATE:THREE.MOUSE.PAN,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.ROTATE}} touches={{ONE:THREE.TOUCH.PAN,TWO:THREE.TOUCH.DOLLY_ROTATE}} maxPolarAngle={Math.PI/2.03} minDistance={2} maxDistance={span*4} makeDefault/><ExploreCamera remoteLook={lookOffset} cacheKey={`${focusBox?"focus-":""}${geometry.building.id}-${multi?scope:floorId}-${exploded}-${focusRequest?`${focusRequest.id}-${focusRequest.revision}`:visualResult?.id??"explore"}`} fitVersion={fitVersion} box={focusBox??fitBox} height={multi?Math.max(...floors.map(f=>elevation(f.id)+f.height_m))-Math.min(...floors.map(f=>elevation(f.id))):3.8} elevation={multi?Math.min(...floors.map(f=>elevation(f.id))):elevation(floorId)} action={action}/></>}

      <SceneLabels labels={sceneLabels} onProject={setProjectedLabels}/>
      {follow&&route&&model&&<VrRig card={guideCard(route,model,time,sample?.step??0)} onToggle={()=>setPlaying(v=>!v)}/>}
      </XR>
    </Canvas>
    {!follow&&<div className="scene-label-layer">{projectedLabels.map(l=><div key={l.id} style={{position:"absolute",left:l.x,top:l.y,transform:"translate(-50%,-50%)"}}>{l.icon?<span className="connector-icon" title={l.text}><Pictogram name={l.icon} size={17}/></span>:<span className="world-label selected-label">{l.text}</span>}</div>)}</div>}
    {follow&&sample?.transition&&<div className="landing-transition"><span>⇅</span><b>Changing floors</b><p>{geometry.floors.find(f=>f.id===sample.point?.floor_id)?.name}</p><small>Landing preview · interior geometry not surveyed</small></div>}
    {follow&&route&&model&&<GuidePlayer route={route} model={model} time={time} speed={speed} playing={playing} step={activeStep} reduced={reduced} transition={sample?.transition?"Floor transition":null}
      onSeek={seek} onPlay={()=>{if(!previewMode)onPreview?.();if(sample?.arrived)seek(0);setPlaying(v=>sample?.arrived?true:!v);}}
      onPrevious={()=>{setPlaying(false);seek(model.chapters[activeStep-1]??0);}} onNext={()=>{setPlaying(false);seek(model.chapters[Math.min(activeStep+1,model.chapters.length-1)]??model.duration);}}
      onSpeed={setSpeed} onRepeat={onRepeat} onExit={()=>{setPlaying(false);onFinish?.();}}/>}
    {!follow&&route&&!visualResult&&<div className="k-status"><button type="button" className="k-pill" data-testid="focus-toggle" aria-pressed={focus} onClick={()=>setFocus(v=>!v)}>{focus?<><b>Route only</b><span>{hiddenCount} other rooms dimmed</span><u>Show everything</u></>:<><b>Everything</b><span>All rooms shown</span><u>Show route only</u></>}</button></div>}
    {!follow&&<div className="k-cam" aria-label="3D camera controls"><Dock col>
      <IconButton label={orbiting?"Move building":"Rotate building"} icon={orbiting?"orbit":"hand"} pressed={orbiting} onClick={()=>setOrbiting(!orbiting)}/>
      <IconButton label="Fit building" icon="fit" onClick={()=>setFitVersion(v=>v+1)}/>
      <IconButton label="Zoom in" icon="plus" onClick={()=>setAction(v=>({id:v.id+1,kind:"zoom-in"}))}/>
      <IconButton label="Zoom out" icon="minus" onClick={()=>setAction(v=>({id:v.id+1,kind:"zoom-out"}))}/>
    </Dock></div>}
    {!follow&&<div className="k-info"><Popover label="About this model" icon="info" open={infoOpen} onOpenChange={setInfoOpen} up>
      <div className="k-pop-title">About this model</div>
      <p className="k-note">Schematic model from the supplied footprints and floor elevations. Furniture and equipment shapes are illustrative.{explode?" Floors are pulled 2 m apart for inspection.":""}</p>
      <div className="k-pop-title">Controls</div>
      <p className="k-note">Drag to move · right-drag to rotate · scroll to zoom · Space plays Guide me.</p>
    </Popover></div>}
  </div>;

}
export default Building3D;

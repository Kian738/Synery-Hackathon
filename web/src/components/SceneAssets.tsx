import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import type { Asset } from "../lib/types";
import { facingTable } from "../lib/facing";
import { getAssetVisual, DEFAULT_FOOTPRINT_M, type AssetPart } from "../scene-assets/catalog";

type Part=AssetPart & {asset:Asset;facing:number};

// Orientation lives in lib/facing.ts: the dataset's rotation 0 puts an item's front toward the wall behind it (measured by `eval.orientation`);
// seating is turned toward the nearest table or screen because its dataset rotation carries no signal.

/** Soft ambient-occlusion look: every unit shape is darker toward its underside, so legs, drawers and undersides read as depth
 *  without any extra lights. The vertex colour multiplies the per-instance colour. */
function shade<T extends THREE.BufferGeometry>(g:T):T{
  const pos=g.getAttribute("position"),colors=new Float32Array(pos.count*3);
  for(let i=0;i<pos.count;i++){const k=0.58+0.42*Math.min(1,Math.max(0,pos.getY(i)+0.5));colors.set([k,k,k],i*3);}
  g.setAttribute("color",new THREE.BufferAttribute(colors,3));return g;
}
/** Geometry is shared by every floor (one copy per shape and detail level, never disposed). Far detail is a plain box, a 10-sided
 *  cylinder and a coarse sphere: at overview distance the rounded edges are sub-pixel, and the triangle count drops by an order of magnitude. */
const GEOMETRY_CACHE=new Map<string,THREE.BufferGeometry>();
function geometryFor(shape:AssetPart['shape'],near:boolean):THREE.BufferGeometry{
  const key=`${shape}|${near}`;let g=GEOMETRY_CACHE.get(key);
  if(!g){
    g=shape==="box"?(near?new RoundedBoxGeometry(1,1,1,2,0.09):new THREE.BoxGeometry(1,1,1))
      :shape==="cylinder"?new THREE.CylinderGeometry(.5,.5,1,near?24:10,1)
      :new THREE.SphereGeometry(.5,near?20:8,near?14:6);
    shade(g);GEOMETRY_CACHE.set(key,g);
  }
  return g;
}
function Instances({parts,shape,elevation,highlighted,muted,near}:{parts:Part[];shape:AssetPart['shape'];elevation:number;highlighted:boolean;muted:boolean;near:boolean}){
  const ref=useRef<THREE.InstancedMesh>(null);
  const geometry=useMemo(()=>geometryFor(shape,near),[shape,near]);
  useEffect(()=>{
    const mesh=ref.current;if(!mesh)return;
    const parent=new THREE.Object3D(),local=new THREE.Object3D();
    for(let i=0;i<parts.length;i++){
      const p=parts[i],a=p.asset,f=a.footprint;
      const width=f&&Number.isFinite(f.width_m)&&f.width_m>0?f.width_m:DEFAULT_FOOTPRINT_M;
      const depth=f&&Number.isFinite(f.depth_m)&&f.depth_m>0?f.depth_m:DEFAULT_FOOTPRINT_M;
      parent.position.set(a.position[0],0,-a.position[1]);parent.rotation.set(0,THREE.MathUtils.degToRad(p.facing),0);parent.updateMatrix();
      local.position.set(p.position[0]*width,p.position[1]+0.005,p.position[2]*depth);
      local.rotation.set(...(p.rotation??[0,0,0]));local.scale.set(p.scale[0]*width,p.scale[1],p.scale[2]*depth);local.updateMatrix();
      mesh.setMatrixAt(i,parent.matrix.clone().multiply(local.matrix));
      mesh.setColorAt(i,new THREE.Color(highlighted?"#ffd45c":p.color).lerp(new THREE.Color("#536670"),muted?.4:0));
    }
    mesh.instanceMatrix.needsUpdate=true;if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;mesh.computeBoundingSphere();
  },[parts,highlighted,muted]);
  if(!parts.length)return null;
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]} castShadow={near} receiveShadow={near}>
    <primitive object={geometry} attach="geometry"/>
    <meshStandardMaterial vertexColors roughness={.62} metalness={.1}/>
  </instancedMesh></group>;
}
export function SceneAssets({assets,context,rings,elevation,highlighted=false,muted=false,interior=false,near=true}:{assets:Asset[];context?:Asset[];rings?:Map<string,[number,number][]>;elevation:number;highlighted?:boolean;muted?:boolean;interior?:boolean;near?:boolean}){
  const groups=useMemo(()=>{
    const groups:{box:Part[];cylinder:Part[];sphere:Part[]}={box:[],cylinder:[],sphere:[]};
    const lod=interior||near?"interior":"overview";
    const facing=facingTable(context??assets,rings);
    assets.forEach(asset=>getAssetVisual(asset,lod).parts.forEach(p=>groups[p.shape].push({...p,asset,facing:facing.get(asset.id)??0})));
    return groups;
  },[assets,context,rings,interior,near]);
  return <>{(["box","cylinder","sphere"] as const).map(shape=><Instances key={shape} shape={shape} parts={groups[shape]} elevation={elevation} highlighted={highlighted} muted={muted} near={interior||near}/>)}</>;
}

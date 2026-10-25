import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Asset } from "../lib/types";
import { getAssetVisual, DEFAULT_FOOTPRINT_M, type AssetPart } from "../scene-assets/catalog";

type Part=AssetPart & {asset:Asset};
function Instances({parts,shape,elevation,highlighted,muted}:{parts:Part[];shape:AssetPart['shape'];elevation:number;highlighted:boolean;muted:boolean}){
  const ref=useRef<THREE.InstancedMesh>(null);
  useEffect(()=>{
    const mesh=ref.current;if(!mesh)return;
    const parent=new THREE.Object3D(),local=new THREE.Object3D();
    for(let i=0;i<parts.length;i++){
      const p=parts[i],a=p.asset,f=a.footprint;
      const width=f&&Number.isFinite(f.width_m)&&f.width_m>0?f.width_m:DEFAULT_FOOTPRINT_M;
      const depth=f&&Number.isFinite(f.depth_m)&&f.depth_m>0?f.depth_m:DEFAULT_FOOTPRINT_M;
      parent.position.set(a.position[0],0,-a.position[1]);parent.rotation.set(0,THREE.MathUtils.degToRad(f?.rotation_deg??0),0);parent.updateMatrix();
      local.position.set(p.position[0]*width,p.position[1]+0.005,p.position[2]*depth);
      local.rotation.set(...(p.rotation??[0,0,0]));local.scale.set(p.scale[0]*width,p.scale[1],p.scale[2]*depth);local.updateMatrix();
      mesh.setMatrixAt(i,parent.matrix.clone().multiply(local.matrix));
      mesh.setColorAt(i,new THREE.Color(highlighted?"#ffd45c":p.color).lerp(new THREE.Color("#536670"),muted?.4:0));
    }
    mesh.instanceMatrix.needsUpdate=true;if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;mesh.computeBoundingSphere();
  },[parts,highlighted,muted]);
  if(!parts.length)return null;
  return <group position={[0,elevation,0]}><instancedMesh ref={ref} args={[undefined,undefined,parts.length]}>
    {shape==="box"?<boxGeometry/>:shape==="cylinder"?<cylinderGeometry args={[.5,.5,1,10]}/>:<sphereGeometry args={[.5,10,7]}/>}
    <meshStandardMaterial roughness={.8} metalness={.12}/>
  </instancedMesh></group>;
}
export function SceneAssets({assets,elevation,highlighted=false,muted=false,interior=false}:{assets:Asset[];elevation:number;highlighted?:boolean;muted?:boolean;interior?:boolean}){
  const groups=useMemo(()=>{
    const groups:{box:Part[];cylinder:Part[];sphere:Part[]}={box:[],cylinder:[],sphere:[]};
    assets.forEach(asset=>getAssetVisual(asset,interior?"interior":"overview").parts.forEach(p=>groups[p.shape].push({...p,asset})));
    return groups;
  },[assets,interior]);
  return <>{(["box","cylinder","sphere"] as const).map(shape=><Instances key={shape} shape={shape} parts={groups[shape]} elevation={elevation} highlighted={highlighted} muted={muted}/>)}</>;
}

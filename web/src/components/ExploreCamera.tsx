import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

const memory=new Map<string,{position:THREE.Vector3;target:THREE.Vector3}>();
export function ExploreCamera({box,height,elevation,cacheKey,fitVersion,action,remoteLook}:{
  box:{minX:number;maxX:number;minY:number;maxY:number};height:number;elevation:number;cacheKey:string;fitVersion:number;remoteLook?:{yaw:number;pitch:number};action:{id:number;kind:string};
}) {
  const {camera,controls,size,invalidate,gl}=useThree();
  const initialized=useRef(false),previousFit=useRef(fitVersion);
  const goal=useRef<{position:THREE.Vector3;target:THREE.Vector3}|null>(null);
  const previousRemote=useRef(remoteLook??{yaw:0,pitch:0});
  const reduced=matchMedia("(prefers-reduced-motion: reduce)").matches;
  const move=(position:THREE.Vector3,target:THREE.Vector3)=>{
    const c=controls as any;if(!c)return;
    if(!initialized.current||reduced){camera.position.copy(position);c.target.copy(target);c.update();goal.current=null;}
    else goal.current={position,target};
    initialized.current=true;invalidate();
  };
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const cancel=()=>{goal.current=null;};c.addEventListener("start",cancel);
    return()=>c.removeEventListener("start",cancel);
  },[controls]);
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const saved=memory.get(cacheKey);
    if(saved&&previousFit.current===fitVersion)move(saved.position.clone(),saved.target.clone());
    else {
      const target=new THREE.Vector3((box.minX+box.maxX)/2,elevation+Math.min(height/2,1),-(box.minY+box.maxY)/2);
      const radius=Math.hypot(box.maxX-box.minX,box.maxY-box.minY,height)/2;
      const vertical=40*Math.PI/180,horizontal=2*Math.atan(Math.tan(vertical/2)*size.width/Math.max(1,size.height));
      const distance=radius/Math.sin(Math.min(vertical,horizontal)/2)*1.06;
      move(target.clone().add(new THREE.Vector3(.65,.8,.8).normalize().multiplyScalar(distance)),target);
    }
    previousFit.current=fitVersion;
    return()=>{memory.set(cacheKey,{position:camera.position.clone(),target:c.target.clone()});if(memory.size>64)memory.delete(memory.keys().next().value!);};
  },[box,height,elevation,cacheKey,fitVersion,controls]);
  useEffect(()=>{
    const c=controls as any;if(!c||!action.id)return;
    const target=c.target.clone(),offset=camera.position.clone().sub(target);
    if(action.kind==="zoom-in"||action.kind==="zoom-out")move(target.clone().add(offset.multiplyScalar(action.kind==="zoom-in"?.8:1.25)),target);
  },[action,controls]);
  useEffect(()=>{
    if(!remoteLook)return;const old=previousRemote.current;previousRemote.current=remoteLook;
    const c=controls as any;if(!c)return;
    const yaw=((remoteLook.yaw-old.yaw+540)%360)-180,pitch=remoteLook.pitch-old.pitch;
    if(Math.abs(yaw)+Math.abs(pitch)<.001)return;
    const target=(goal.current?.target??c.target).clone();
    const sphere=new THREE.Spherical().setFromVector3((goal.current?.position??camera.position).clone().sub(target));
    sphere.theta-=THREE.MathUtils.degToRad(yaw);sphere.phi=THREE.MathUtils.clamp(sphere.phi-THREE.MathUtils.degToRad(pitch),.12,Math.PI/2.03);
    move(target.clone().add(new THREE.Vector3().setFromSpherical(sphere)),target);
  },[remoteLook,controls]);
  useFrame((_,dt)=>{
    camera.updateMatrixWorld();const el=gl.domElement;el.dataset.cameraPosition=JSON.stringify(camera.position.toArray());el.dataset.cameraQuaternion=JSON.stringify(camera.quaternion.toArray());
    const c=controls as any,g=goal.current;if(!c||!g)return;
    const alpha=1-Math.exp(-12*Math.min(dt,.1));
    camera.position.lerp(g.position,alpha);c.target.lerp(g.target,alpha);c.update();
    if(camera.position.distanceToSquared(g.position)+c.target.distanceToSquared(g.target)<.0001){camera.position.copy(g.position);c.target.copy(g.target);goal.current=null;c.update();}
    invalidate();
  });
  return null;
}

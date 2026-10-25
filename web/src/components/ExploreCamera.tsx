import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { ease } from "../lib/focus";

const memory=new Map<string,{position:THREE.Vector3;target:THREE.Vector3}>();
export function ExploreCamera({box,height,elevation,cacheKey,fitVersion,action,remoteLook}:{
  box:{minX:number;maxX:number;minY:number;maxY:number};height:number;elevation:number;cacheKey:string;fitVersion:number;remoteLook?:{yaw:number;pitch:number};action:{id:number;kind:string};
}) {
  const {camera,controls,size,invalidate,gl}=useThree();
  const initialized=useRef(false),previousFit=useRef(fitVersion);
  // A fixed-length eased flight from where the camera is to the goal (an exponential chase covered 90% of a cross-building move in 0.2 s).
  const goal=useRef<{position:THREE.Vector3;target:THREE.Vector3;from:THREE.Vector3;fromTarget:THREE.Vector3;elapsed:number;duration:number}|null>(null);
  const previousRemote=useRef(remoteLook??{yaw:0,pitch:0});
  const reduced=matchMedia("(prefers-reduced-motion: reduce)").matches;
  const move=(position:THREE.Vector3,target:THREE.Vector3,quick=false)=>{
    const c=controls as any;if(!c)return;
    if(!initialized.current||reduced){camera.position.copy(position);c.target.copy(target);c.update();goal.current=null;}
    else {
      const travel=camera.position.distanceTo(position)+c.target.distanceTo(target);
      goal.current={position,target,from:camera.position.clone(),fromTarget:c.target.clone(),elapsed:0,duration:quick?0:THREE.MathUtils.clamp(.7+travel*.02,.9,1.6)};
    }
    initialized.current=true;invalidate();
  };
  useEffect(()=>{
    const c=controls as any;if(!c)return;
    const cancel=()=>{goal.current=null;};c.addEventListener("start",cancel);
    return()=>c.removeEventListener("start",cancel);
  },[controls]);
  const boxKey=`${box.minX.toFixed(2)},${box.maxX.toFixed(2)},${box.minY.toFixed(2)},${box.maxY.toFixed(2)}`;
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
    // Remember where the camera is headed, not a point halfway through a flight (restoring that froze the camera mid-move).
    return()=>{const g=goal.current;memory.set(cacheKey,{position:(g?.position??camera.position).clone(),target:(g?.target??c.target).clone()});if(memory.size>64)memory.delete(memory.keys().next().value!);};
  },[boxKey,height,elevation,cacheKey,fitVersion,controls]);
  useEffect(()=>{
    const c=controls as any;if(!c||!action.id)return;
    const target=c.target.clone(),offset=camera.position.clone().sub(target);
    if(action.kind==="zoom-in"||action.kind==="zoom-out")move(target.clone().add(offset.multiplyScalar(action.kind==="zoom-in"?.8:1.25)),target,true);
  },[action,controls]);
  useEffect(()=>{
    if(!remoteLook)return;const old=previousRemote.current;previousRemote.current=remoteLook;
    const c=controls as any;if(!c)return;
    const yaw=((remoteLook.yaw-old.yaw+540)%360)-180,pitch=remoteLook.pitch-old.pitch;
    if(Math.abs(yaw)+Math.abs(pitch)<.001)return;
    const target=(goal.current?.target??c.target).clone();
    const sphere=new THREE.Spherical().setFromVector3((goal.current?.position??camera.position).clone().sub(target));
    sphere.theta-=THREE.MathUtils.degToRad(yaw);sphere.phi=THREE.MathUtils.clamp(sphere.phi-THREE.MathUtils.degToRad(pitch),.12,Math.PI/2.03);
    move(target.clone().add(new THREE.Vector3().setFromSpherical(sphere)),target,true);
  },[remoteLook,controls]);
  useFrame((_,dt)=>{
    camera.updateMatrixWorld();const el=gl.domElement;el.dataset.cameraPosition=JSON.stringify(camera.position.toArray());el.dataset.cameraQuaternion=JSON.stringify(camera.quaternion.toArray());
    const c=controls as any,g=goal.current;if(!c||!g)return;
    if(!g.duration){ // small, possibly streamed nudges (zoom buttons, remote look): a quick chase that follows a moving goal without restarting
      const alpha=1-Math.exp(-12*Math.min(dt,.1));
      camera.position.lerp(g.position,alpha);c.target.lerp(g.target,alpha);c.update();
      if(camera.position.distanceToSquared(g.position)+c.target.distanceToSquared(g.target)<.0001){camera.position.copy(g.position);c.target.copy(g.target);goal.current=null;c.update();}
    } else {
      g.elapsed+=Math.min(dt,.1);const k=ease(Math.min(1,g.elapsed/g.duration));
      camera.position.lerpVectors(g.from,g.position,k);c.target.lerpVectors(g.fromTarget,g.target,k);c.update();
      if(k>=1)goal.current=null;
    }
    invalidate();
  });
  return null;
}

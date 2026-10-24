import {useFrame,useThree} from "@react-three/fiber";
import {useMemo,useRef} from "react";
import * as THREE from "three";

export interface SceneLabel {id:string;position:[number,number,number];text:string;icon?:string}
export interface ProjectedLabel extends SceneLabel {x:number;y:number}
/** DOM labels stay in Navigator's React tree. Separate DOM roots inside the canvas
 * can race their teardown when a remote step changes view and floor together. */
export function SceneLabels({labels,onProject}:{labels:SceneLabel[];onProject:(labels:ProjectedLabel[])=>void}){
  const {camera,size,scene}=useThree();
  const ray=useMemo(()=>new THREE.Raycaster(),[]),last=useRef("");
  useFrame(()=>{
    if(!labels.length){if(last.current!=="[]"){last.current="[]";onProject([]);}return;}
    const walls:THREE.Object3D[]=[];scene.traverse(o=>{if(o.userData.labelOccluder)walls.push(o);});
    const projected:ProjectedLabel[]=[];
    for(const label of labels){
      const world=new THREE.Vector3(...label.position),p=world.clone().project(camera);
      if(p.z< -1||p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1)continue;
      const direction=world.clone().sub(camera.position),distance=direction.length();
      ray.set(camera.position,direction.normalize());ray.near=0;ray.far=Math.max(0,distance-.05);
      if(ray.intersectObjects(walls,false).length)continue;
      projected.push({...label,x:Math.round((p.x+1)*size.width/2),y:Math.round((1-p.y)*size.height/2)});
    }
    const key=JSON.stringify(projected);if(key!==last.current){last.current=key;onProject(projected);}
  });return null;
}

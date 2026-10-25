import fs from 'node:fs';import {build} from 'esbuild';import {createRequire} from 'node:module';import {fileURLToPath} from 'node:url';
import {alignStairFrame} from '../src/lib/stairFrame.ts';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const compiled=await build({stdin:{contents:"export {orientedRect,stairBoxes} from './src/components/Connectors3D';export * as THREE from 'three';",sourcefile:'shaft-fixture.ts',resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'cjs',jsx:'automatic',write:false});
const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports);const {orientedRect,stairBoxes,THREE}=mod.exports;
const spaces=new Map(input.data.spaces.map(s=>[s.id,s])),floors=new Map(input.data.floors.map(f=>[f.id,f]));const output=[];
for(const shaft of input.shafts){
 if(!shaft.footprint)continue;
 const c=input.data.vertical_connectors.find(c=>c.id===shaft.connector_id),lower=spaces.get(c.space_ids[c.floor_ids.indexOf(shaft.from_floor)]),upper=spaces.get(c.space_ids[c.floor_ids.indexOf(shaft.to_floor)]);
 const doors=s=>input.data.openings.filter(o=>o.space_ids.includes(s.id)).map(o=>o.position);const frame=alignStairFrame(orientedRect(shaft.footprint),doors(lower),doors(upper));
 const boxes=stairBoxes(lower,0,floors.get(upper.floor_id).elevation_m-floors.get(lower.floor_id).elevation_m,false,frame);
 const footprints=boxes.map(b=>{const q=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),b.yaw).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),b.tilt));const pts=[];for(const x of [-1,1])for(const y of [-1,1])for(const z of [-1,1]){const p=new THREE.Vector3(x*b.sx/2,y*b.sy/2,z*b.sz/2).applyQuaternion(q).add(new THREE.Vector3(b.x,b.y,b.z));pts.push([p.x,-p.z]);}return pts;});
 output.push({lower:lower.id,upper:upper.id,footprints});
}
console.log(JSON.stringify(output));

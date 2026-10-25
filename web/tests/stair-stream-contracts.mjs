import assert from 'node:assert/strict';
import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';import {fileURLToPath} from 'node:url';

import {build} from 'esbuild';
import {readEvents} from '../src/lib/api.ts';
import {alignStairFrame} from '../src/lib/stairFrame.ts';
import {startAssistantStream,appendAssistantText} from '../src/lib/chatStream.ts';
let id=0;let messages=appendAssistantText([],'early','Hello',()=>++id);
assert.equal(messages[0].text,'Hello');messages=startAssistantStream(messages,'early','Claude',()=>++id);assert.equal(messages.length,1);assert.equal(messages[0].text,'Hello');
messages=appendAssistantText(messages,'early',' world',()=>++id);assert.equal(messages[0].text,'Hello world');messages=startAssistantStream(messages,'early','Claude',()=>++id);assert.equal(messages.length,1);
messages=appendAssistantText(messages,'next','Second round',()=>++id);assert.equal(messages.length,2);assert.equal(messages[0].text,'Hello world');
const fixture=await build({stdin:{contents:"export {orientedRect,stairBoxes} from './src/components/Connectors3D';export * as THREE from 'three';export * as React from 'react';export {renderToStaticMarkup} from 'react-dom/server';export {AgentReply} from './src/components/AgentReply';",sourcefile:'stairs.ts',resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'cjs',jsx:'automatic',write:false});
const mod={exports:{}};new Function('require','module','exports',fixture.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports);
const {orientedRect,stairBoxes,THREE}=mod.exports;
const kit=process.env.FLOORWISE_KIT??path.resolve('docs/industrial-agents-hackathon-2026');const data=JSON.parse(fs.readFileSync(path.join(kit,'data/dev/osm-way27917482/building.json'),'utf8'));const spaces=new Map(data.spaces.map(s=>[s.id,s]));const floors=new Map(data.floors.map(f=>[f.id,f]));
for(const [suffix,sign] of [['V20',-1],['V21',1],['V22',1],['V23',-1],['V24',1],['V25',-1]]){
 const c=data.vertical_connectors.find(c=>c.id.endsWith('-'+suffix));const lower=spaces.get(c.space_ids[0]),upper=spaces.get(c.space_ids[1]);const low=data.openings.filter(o=>o.space_ids.includes(lower.id)).map(o=>o.position),high=data.openings.filter(o=>o.space_ids.includes(upper.id)).map(o=>o.position);
 const frame=alignStairFrame(orientedRect(lower.polygon),low,high);assert.equal(Math.sign(frame.ux),sign,suffix);assert.equal(frame.orientationSource,'mapped_landing_openings');
 const reversed=alignStairFrame(orientedRect([...lower.polygon].reverse()),low,high);assert(Math.abs(frame.ux-reversed.ux)<1e-5,suffix+' winding');
 const rise=floors.get(upper.floor_id).elevation_m-floors.get(lower.floor_id).elevation_m;const boxes=stairBoxes(lower,0,rise,false,frame);const steps=boxes.filter(b=>b.color==='#dde2e0').sort((a,b)=>a.y-b.y);const first=steps[0],last=steps.at(-1);
 assert((last.x-first.x)*(high[0][0]-low[0][0])+(last.z-first.z)*-(high[0][1]-low[0][1])>0,suffix+' ascent');
 const beam=boxes.find(b=>b.color==='#8e9a99');const q=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),beam.yaw).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),beam.tilt));const axis=new THREE.Vector3(1,0,0).applyQuaternion(q);const direction=new THREE.Vector3(last.x-first.x,last.y-first.y,last.z-first.z).normalize();assert(axis.dot(direction)>.999,suffix+' support frame');
}
assert.equal(alignStairFrame({cx:0,cy:0,ux:-1,uy:0,length:8,width:2},[],[]).orientationSource,'schematic_canonical_axis');
let controller;let ended=false;let live=[];
const pending=readEvents(new Response(new ReadableStream({start(c){controller=c;}})),e=>{if(e.type==='assistant_delta')live=appendAssistantText(live,e.data.message_id,e.data.text,()=>++id);if(e.type==='done')ended=true;});
controller.enqueue(new TextEncoder().encode('data: '+JSON.stringify({type:'assistant_delta',data:{message_id:'live',text:'First words now'}})+'\n\n'));
await new Promise(resolve=>setTimeout(resolve,5));
assert.equal(ended,false);assert.equal(live[0].text,'First words now');
const rendered=mod.exports.renderToStaticMarkup(mod.exports.React.createElement(mod.exports.AgentReply,{text:live[0].text,spaces:[],onRoom:()=>{}}));assert.match(rendered,/First words now/);
controller.enqueue(new TextEncoder().encode('data: {"type":"done","data":null}\n\n'));controller.close();await pending;assert.equal(ended,true);
console.log('All six CIT atrium flights follow mapped upper landings; support frames align. Early/duplicate stream starts preserve text.');

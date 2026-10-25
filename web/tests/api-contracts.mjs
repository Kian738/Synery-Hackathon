import assert from 'node:assert/strict';
import {roomMentions} from '../src/lib/roomMentions.ts';
import {readEvents,chat} from '../src/lib/api.ts';

const encoder=new TextEncoder();
const chunks=['data: {"type":"assistant_delta","data":{"text":"hé','llo"}}\r','\n\r\ndata: {"type":"done","data":null}\n\n'];
const response=new Response(new ReadableStream({start(controller){const wire=encoder.encode(chunks.join(""));for(let i=0;i<wire.length;i++)controller.enqueue(wire.slice(i,i+1));controller.close();}}));
const events=[];await readEvents(response,e=>events.push(e));
assert.equal(events[0].data.text,'héllo');assert.equal(events[1].type,'done');
let cancelled=false;
await assert.rejects(()=>readEvents(new Response(new ReadableStream({start(c){c.enqueue(encoder.encode('data: not-json\n\n'));},cancel(){cancelled=true;}})),()=>{}),/invalid event/);
assert.equal(cancelled,true);
const original=globalThis.fetch;
try{
  globalThis.fetch=async()=>new Response('data: {"type":"assistant_delta","data":{"text":"partial"}}\n\n');
  await assert.rejects(()=>chat('fixture','hello',()=>{}),/Connection ended/);
  globalThis.fetch=async()=>new Response('data: {"type":"done","data":null}\n\n');
  await chat('fixture','hello',()=>{});
}finally{globalThis.fetch=original;}
console.log('Frontend stream contracts passed without a browser or network.');

const spaces=[{id:'a',name:'Lab 2.08',ref:'2.08'},{id:'b',name:'Office',ref:null},{id:'c',name:'Office',ref:null}];
assert.equal(roomMentions('Walk to Lab 2.08.',spaces)[0].id,'a');
assert.equal(roomMentions('The area is 2.08 m2. Office',spaces).length,0);
assert.deepEqual(roomMentions('Lab 2.08 then Lab 2.08',spaces),roomMentions('Lab 2.08 then Lab 2.08',spaces));

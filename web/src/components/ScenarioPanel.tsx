import {useState} from 'react';
import type {Geometry,UiEvent} from '../lib/types';

export function ScenarioPanel({geometry,sessionId,room,onClose,onResult}:{geometry:Geometry;sessionId:string;room:string|null;onClose:()=>void;onResult:(events:UiEvent[])=>void}){
  const [origin,setOrigin]=useState(room??geometry.spaces.find(s=>s.type==='room')?.id??'');
  const [people,setPeople]=useState(''),[rate,setRate]=useState(''),[closed,setClosed]=useState(''),[entrance,setEntrance]=useState(''),[target,setTarget]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const spaces=new Map(geometry.spaces.map(s=>[s.id,s.name]));
  const openingLabel=(o:Geometry['openings'][number])=>o.space_ids.map(s=>s==='outside'?'Outside':spaces.get(s)??s).join(' ↔ ');
  const run=async()=>{setBusy(true);setError('');try{
    const response=await fetch(`/api/sessions/${sessionId}/scenario`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({occupants:{[origin]:Number(people)},door_rate_per_minute:Number(rate),closed:closed?[closed]:[],responder_target:target||null,responder_entrance:entrance||null})});
    const body=await response.json();if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'Check the scenario inputs.');onResult(body.events);onClose();
  }catch(e){setError(String(e));}finally{setBusy(false);}};
  return <section className="scenario-panel" aria-label="Scenario inputs"><header><div><span>Hypothetical capacity model</span><h2>What changes?</h2></div><button aria-label="Close scenarios" onClick={onClose}>Close</button></header>
    <p>Set assumptions explicitly. Running a scenario does not edit the building or change your location.</p>
    <label>Occupied room<select aria-label="Occupied room" value={origin} onChange={e=>setOrigin(e.target.value)}>{geometry.spaces.filter(s=>s.type==='room'||s.type==='hall').map(s=><option key={s.id} value={s.id}>{s.name} · {geometry.floors.find(f=>f.id===s.floor_id)?.name}</option>)}</select></label>
    <label>People in this room<input aria-label="People in this room" type="number" min={1} max={1000} step={1} value={people} placeholder="Enter occupancy" onChange={e=>setPeople(e.target.value)}/></label>
    <label>Assumed passage limit · people/minute per opening<input aria-label="People per minute" type="number" min={.1} max={10000} value={rate} placeholder="Enter passage rate" onChange={e=>setRate(e.target.value)}/></label>
    <label>Compare a blocked passage<select aria-label="Blocked passage" value={closed} onChange={e=>setClosed(e.target.value)}><option value="">No additional blockage</option>{geometry.connectors.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}{geometry.openings.filter(o=>o.space_ids.includes('outside')).map(o=><option key={o.id} value={o.id}>{openingLabel(o)}</option>)}</select></label>
    <details><summary>Responder entrance and target</summary><label>Responder entrance<select aria-label="Responder entrance" value={entrance} onChange={e=>setEntrance(e.target.value)}><option value="">No responder reservation</option>{geometry.openings.filter(o=>o.space_ids.includes('outside')).map(o=><option key={o.id} value={o.id}>{openingLabel(o)}</option>)}</select></label><label>Responder target<select aria-label="Responder target" value={target} onChange={e=>setTarget(e.target.value)}><option value="">Choose a target</option>{geometry.spaces.filter(s=>s.type==='room').map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label></details>
    <details><summary>Model assumptions</summary><p>5-second discrete steps, 300-second horizon, walking 1.34 m/s, stairs at 0.7× walking speed, lifts excluded. All mapped openings use your assumed rate. Model flow lines use room anchors; they are separate from validated walking previews. These assumptions appear with the result.</p></details>
    {error&&<p role="alert">{error}</p>}<button className="scenario-run" disabled={busy||!origin||!people||!rate||Number(people)<=0||Number(rate)<=0||!!entrance!==!!target} onClick={()=>void run()}>{busy?'Computing flows…':'Compare scenario'}</button>
  </section>;
}

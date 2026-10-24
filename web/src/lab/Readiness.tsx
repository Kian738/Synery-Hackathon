import {useEffect,useState} from 'react';
import {Link} from 'react-router';
import {lab} from '../lib/api';

export default function Readiness(){
  const [report,setReport]=useState<any>(null),[features,setFeatures]=useState<any[]>([]),[error,setError]=useState(''),[job,setJob]=useState(''),[lines,setLines]=useState<string[]>([]);
  const reload=()=>{setError('');Promise.all([fetch('/api/lab/readiness').then(r=>{if(!r.ok)throw Error('Readiness unavailable');return r.json();}),fetch('/api/lab/features').then(r=>r.json())]).then(([r,f])=>{setReport(r);setFeatures(f);}).catch(e=>setError(e.message));};
  useEffect(reload,[]);
  const run=async(profile:string)=>{setError('');setLines([]);try{const response=await fetch('/api/lab/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile})});if(!response.ok)throw Error(await response.text());const {id}=await response.json();setJob(id);await lab.stream(id,event=>{if(event.type==='line')setLines(all=>[...all.slice(-29),event.text??'']);});reload();}catch(e){setError(String(e));}finally{setJob('');}};
  return <div className="readiness-page"><header><h1>Release readiness</h1><p>Evidence for the jury’s four criteria. No guessed overall score.</p><div className="readiness-actions">{['smoke','full','live','demo'].map(profile=><button disabled={!!job} key={profile} onClick={()=>void run(profile)}>Run {profile}{profile==='live'||profile==='demo'?' · uses Claude':''}</button>)}{job&&<button onClick={()=>void fetch(`/api/lab/jobs/${job}/cancel`,{method:'POST'})}>Stop run</button>}</div></header>
    {error&&<div role="alert">{error}<button onClick={reload}>Retry loading</button></div>}
    {!report&&!error&&<p role="status">Loading versioned evidence…</p>}
    {lines.length>0&&<details open><summary>Current run</summary><pre className="readiness-log">{lines.join('\n')}</pre></details>}
    {report&&<><p className="readiness-version">Source {report.fingerprint.source} · kit {report.fingerprint.kit_git.slice(0,8)} · {report.fingerprint.provider}. Historical runs cannot prove this build works.</p><div className="judging-panels">{report.groups.map((group:any)=><section key={group.id}><h2>{group.title} <span>{group.points} points</span></h2>{report.requirements.filter((r:any)=>r.group===group.id).map((r:any)=><article key={r.id} data-status={r.status}><div><strong>{r.title}</strong><span className="readiness-state">{r.status}</span></div><p>{r.latest?`${r.latest.correct}/${r.latest.total} raw checks · ${r.latest.known_failures??0} known misses · ${r.latest.unexplained_failures??0} unexplained`:'No evidence recorded'}</p>{r.latest?.outcomes&&<p>{Object.entries(r.latest.outcomes).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>}<div className="readiness-links"><a href={r.source} target="_blank" rel="noreferrer">{r.source_section}</a>{r.latest?.run&&<Link to={`/lab/runs/${r.latest.run}`}>Inspect evidence</Link>}</div></article>)}</section>)}</div>
    <section><h2>Release blockers <span>{report.blockers.length}</span></h2><ul>{report.blockers.map((r:any)=><li key={r.id}>{r.title}: {r.status} — run {r.suite} and inspect failures.</li>)}</ul></section>
    <section><h2>Find every feature</h2><p>Implemented, accessible and verified are different claims.</p><div className="feature-inventory">{features.map(f=><article key={f.id}><strong>{f.title}</strong><span>{f.status}</span><p>{f.location}</p></article>)}</div></section><p>{report.notice}</p><Link to="/lab/checks">Detailed benchmark checks</Link></>}
  </div>;
}

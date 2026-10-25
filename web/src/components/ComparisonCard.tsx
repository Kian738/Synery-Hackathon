import {useEffect,useMemo,useState} from 'react';
import {api} from '../lib/api';
import {downloadCsv} from '../lib/share';
import type {VisualResult} from '../lib/types';
type Scope={scope:string;total:number;maximum:number;leader_ids:string[];leaders:string[]};
type Row={label:string;item_type:string;scopes:Scope[]};
export function ComparisonCard({result,session,onPick,onClose}:{result:VisualResult;session:string;onPick:(id:string)=>void;onClose:()=>void}){
  const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState(''),[query,setQuery]=useState(''),[retry,setRetry]=useState(0),[loading,setLoading]=useState(true);
  useEffect(()=>{let cancelled=false;setRows([]);setError('');setLoading(true);(async()=>{let offset=0,all:Row[]=[];
    do{const page=await api.resultPage(session,result.id,offset);if(cancelled)return;all.push(...page.rows as unknown as Row[]);if(page.next_offset===null)break;offset=page.next_offset;}while(!cancelled);
    if(!cancelled)setRows(all);
  })().catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[session,result.id,retry]);
  const shown=useMemo(()=>rows.filter(r=>r.label.toLowerCase().includes(query.trim().toLowerCase())),[rows,query]);
  const scopes=rows[0]?.scopes??[];
  return <section className="visual-answer comparison-card" aria-label="Visual answer">
    <header><span>Every recorded item type</span><button aria-label="Close visual answer" onClick={onClose}>Close</button></header>
    <h2>Where are the most?</h2><p className="result-provenance">{rows.length} types · exact counts · ties included</p>
    <label className="comparison-filter">Filter item types<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. chairs, printers"/></label>
    {loading&&<p role="status">Loading the complete comparison…</p>}{error&&<p role="alert">{error}<button onClick={()=>setRetry(n=>n+1)}>Retry</button></p>}
    {!loading&&!error&&<><div className="comparison-scroll" tabIndex={0} role="region" aria-label="Item leader comparison"><table><thead><tr><th scope="col">Item</th>{scopes.map(s=><th scope="col" key={s.scope}>{s.scope}</th>)}</tr></thead><tbody>{shown.map(row=><tr key={row.item_type}><th scope="row">{row.label}</th>{row.scopes.map(scope=><td key={scope.scope}><b>{scope.total} total</b><span>Most: {scope.maximum}</span>{scope.leaders.slice(0,2).map((name,i)=><button key={scope.leader_ids[i]} onClick={()=>onPick(scope.leader_ids[i])}>{name}</button>)}{scope.leaders.length>2&&<details><summary>All {scope.leaders.length} tied places</summary>{scope.leaders.slice(2).map((name,i)=><button key={scope.leader_ids[i+2]} onClick={()=>onPick(scope.leader_ids[i+2])}>{name}</button>)}</details>}{scope.total===0&&<span>None recorded</span>}</td>)}</tr>)}</tbody></table></div>{!shown.length&&<p>No item types match “{query}”.</p>}
    <button onClick={()=>downloadCsv('floorwise-item-comparison.csv',[['Item',...scopes.flatMap(s=>[s.scope+' total',s.scope+' maximum',s.scope+' leaders'])],...rows.map(r=>[r.label,...r.scopes.flatMap(s=>[s.total,s.maximum,s.leaders.join('; ')])])])}>Export complete comparison</button></>}
    <p className="result-provenance">Recorded equipment counts, not seating capacity or availability. Select a place to inspect it.</p>
  </section>;
}

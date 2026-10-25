import type {Message} from '../navigator/useNavigator';
import type {VisualResult} from '../lib/types';
type Result=Extract<Message,{role:'result'}>;
export function TurnResultLinks({results,floors,onResult,onRerun,busy}:{results:Result[];floors:{id:string;name:string}[];onResult:(r:VisualResult&{total_rows:number})=>void;onRerun:(q:string)=>void;busy:boolean}){
 if(!results.length)return null;
 if(results.length===1)return <div className="answer-reference"><span>{results[0].text}</span><button onClick={()=>onResult(results[0].result)}>View results</button>{results[0].query&&<button disabled={busy} onClick={()=>onRerun(results[0].query!)}>Run again</button>}</div>;
 return <details className="answer-result-group"><summary>{results.length} visual results</summary><ul>{results.map(r=><li key={r.id}><span>{r.text}<small>{r.result.floor_ids.map(id=>floors.find(f=>f.id===id)?.name??id).join(', ')}</small></span><button onClick={()=>onResult(r.result)}>View results</button></li>)}</ul>{results.at(-1)?.query&&<button disabled={busy} onClick={()=>onRerun(results.at(-1)!.query!)}>Refresh these results</button>}</details>;
}

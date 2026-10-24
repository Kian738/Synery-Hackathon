import type { Message } from "../navigator/useNavigator";

type Activity=Extract<Message,{role:"activity"}>;
const NAMES:Record<string,string>={count_items:"Count recorded items",rank_rooms_by_items:"Compare rooms by contents",find_route:"Calculate walking route",search:"Find matching places",room_info:"Inspect room data",set_closed:"Check closure impact",remember_person:"Apply remembered needs",filter_rooms:"Check every requirement",shared_walls:"Measure shared walls",distance_3d:"Measure 3D distance",load_tools:"Enable specialist checks"};
function summary(result:unknown){
  if(!result||typeof result!=="object")return typeof result==="string"?result.slice(0,200):"";
  return Object.entries(result).filter(([key,value])=>typeof value==="number"||key==="scope"||key==="distance_basis").map(([key,value])=>`${key.replaceAll("_"," ")}: ${value}`).join(" · ").slice(0,300);
}
export function ToolTrace({activities,busy}:{activities:Activity[];busy:boolean}){
  if(!activities.length)return null;
  const groups=new Map<string,Activity[]>();activities.forEach(a=>{const key=a.tool??a.text;groups.set(key,[...(groups.get(key)??[]),a]);});
  const pending=activities.filter(a=>a.result===undefined).length;
  return <details className="tool-trace"><summary><span className={busy&&pending?"check-pending":"check-complete"}/>{busy&&pending?"Checking the building":"Building checks"}<span>{activities.length} calls</span></summary>
    <p>Expand a check to inspect its inputs and computed result.</p>
    {[...groups].map(([key,items])=><details key={key}><summary>{NAMES[key]??items[0].text}{items.length>1&&<b>×{items.length}</b>}</summary>{items.map(item=><div className="tool-evidence" key={item.id}>
      <span>{item.failed?"Needs attention":item.result===undefined?(busy?"In progress":"Called"):"Computed"}</span>
      {item.input&&<dl>{Object.entries(item.input).map(([name,value])=><div key={name}><dt>{name.replaceAll("_"," ")}</dt><dd>{typeof value==="string"?value:JSON.stringify(value)}</dd></div>)}</dl>}
      {item.result!==undefined&&<p>{summary(item.result)||"Result returned to the guide."}</p>}
    </div>)}</details>)}
  </details>;
}

import {Fragment,useMemo} from "react";
import {roomMentions} from "../lib/roomMentions";
import type {Space} from "../lib/types";

export function RoomText({text,spaces,onRoom}:{text:string;spaces:Space[];onRoom:(id:string)=>void}){
  const {plain,matches,bold}=useMemo(()=>{
    const plain=text.replace(/\*\*/g,"");let removed=0;const bold:{start:number;end:number}[]=[];
    for(const m of text.matchAll(/\*\*([^*]+)\*\*/g)){const start=m.index!-removed;bold.push({start,end:start+m[1].length});removed+=4;}
    return {plain,bold,matches:roomMentions(plain,spaces)};
  },[text,spaces]);
  const slice=(start:number,end:number)=>{
    const cuts=[...new Set([start,...bold.flatMap(b=>[b.start,b.end]).filter(n=>n>start&&n<end),end])].sort((a,b)=>a-b);
    return cuts.slice(0,-1).map((at,i)=>bold.some(b=>at>=b.start&&at<b.end)?<strong key={at}>{plain.slice(at,cuts[i+1])}</strong>:<Fragment key={at}>{plain.slice(at,cuts[i+1])}</Fragment>);
  };
  let cursor=0;
  const pieces=matches.flatMap(m=>{const before=slice(cursor,m.start);cursor=m.end;return [<Fragment key={`text-${m.start}`}>{before}</Fragment>,<button type="button" className="room-mention" key={`${m.start}-${m.id}`} onClick={()=>onRoom(m.id)} title="Show room in the building">{slice(m.start,m.end)}</button>];});
  return <>{pieces}{slice(cursor,plain.length)}</>;
}

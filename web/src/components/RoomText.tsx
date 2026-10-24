import {useMemo} from "react";
import {roomMentions} from "../lib/roomMentions";
import type {Space} from "../lib/types";

export function RoomText({text,spaces,onRoom}:{text:string;spaces:Space[];onRoom:(id:string)=>void}){
  const matches=useMemo(()=>roomMentions(text,spaces),[text,spaces]);let cursor=0;
  const pieces=matches.flatMap(m=>{const before=text.slice(cursor,m.start);cursor=m.end;return [before,<button className="room-mention" key={`${m.start}-${m.id}`} onClick={()=>onRoom(m.id)} title="Show room in the building">{text.slice(m.start,m.end)}</button>];});
  return <>{pieces}{text.slice(cursor)}</>;
}

import type {Space} from "./types";

export function roomMentions(text:string,spaces:Space[]){
  const names=new Map<string,{label:string;ids:Set<string>}>();
  for(const room of spaces)for(const name of [room.name,room.ref??""]){
    const label=name.trim(),key=label.toLocaleLowerCase();if(key.length<4)continue;
    const entry=names.get(key)??{label,ids:new Set<string>()};entry.ids.add(room.id);names.set(key,entry);
  }
  const found:{start:number;end:number;id:string}[]=[];
  const word=(c:string)=>/[\p{L}\p{N}_]/u.test(c);
  for(const {label:name,ids} of names.values()){
    if(ids.size!==1)continue; // Shared names require clarification, never a guessed link.
    const pattern=new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),"giu");
    for(const match of text.matchAll(pattern)){
      const index=match.index!,end=index+match[0].length;
      if((index&&word(text[index-1]))||(end<text.length&&word(text[end])))continue;
      // A bare decimal can be a measurement. Long dotted room references are distinct.
      if(/^\d+[.]\d+$/.test(name)&&!/(?:room|office|lab|raum|büro|hall)\s*$/iu.test(text.slice(Math.max(0,index-20),index)))continue;
      found.push({start:index,end,id:[...ids][0]});
    }
  }
  found.sort((a,b)=>a.start-b.start||(b.end-b.start)-(a.end-a.start));
  let end=0;return found.filter(m=>{if(m.start<end)return false;end=m.end;return true;});
}

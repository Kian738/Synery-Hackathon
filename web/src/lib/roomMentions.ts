import type {Space} from "./types";

const cache=new WeakMap<Space[],{name:string;id:string;pattern:RegExp}[]>();
function index(spaces:Space[]){
  const saved=cache.get(spaces);if(saved)return saved;
  const names=new Map<string,{label:string;ids:Set<string>}>();
  for(const room of spaces)for(const name of [room.name,room.ref??room.name.match(/\b\d+(?:[.]\d+)+[\p{L}-]*$/u)?.[0]??""]){
    const label=name.trim(),key=label.toLocaleLowerCase();if(key.length<4)continue;
    const entry=names.get(key)??{label,ids:new Set<string>()};entry.ids.add(room.id);names.set(key,entry);
  }
  const entries:{name:string;id:string;pattern:RegExp}[]=[];
  for(const {label:name,ids} of names.values()){
    if(ids.size!==1)continue;
    entries.push({name,id:[...ids][0],pattern:new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),"giu")});
  }
  cache.set(spaces,entries);return entries;
}
export function roomMentions(text:string,spaces:Space[]){
  const found:{start:number;end:number;id:string}[]=[];
  const word=(c:string)=>/[\p{L}\p{N}_]/u.test(c);
  for(const {name,id,pattern} of index(spaces))for(const match of text.matchAll(pattern)){
    const at=match.index!,end=at+match[0].length;
    if((at&&word(text[at-1]))||(end<text.length&&word(text[end])))continue;
    if((text[at-1]==='.'&&/\d/.test(text[at-2]??''))||(text[end]==='.'&&/\d/.test(text[end+1]??'')))continue;
    if(/^\d+[.]\d+$/.test(name)){
      const before=text.slice(Math.max(0,at-45),at),after=text.slice(end);
      const roomContext=/(?:rooms?|offices?|labs?|raum|räume|büros?|halls?|seminar|meeting)\s*[*_]*\s*$/iu.test(before);
      const unit=/^\s*[*_]*\s*(?:m(?:²|2|³|3)?|cm|mm|km|met(?:er|re)s?|feet|ft|kg|seconds?|minutes?|s|%|USD|EUR)(?![\p{L}\p{N}_])|^\s*[*_]*\s*[€$£]/iu.test(after);
      const measurement=/(?:area|distance|height|width|length|depth|size|ratio|value|cost|price|fläche|abstand|höhe|breite)\b[^.!?;:\n]{0,25}$/iu.test(before);
      if(unit||(!roomContext&&measurement))continue;
    }
    found.push({start:at,end,id});
  }
  found.sort((a,b)=>a.start-b.start||(b.end-b.start)-(a.end-a.start));
  let end=0;return found.filter(m=>{if(m.start<end)return false;end=m.end;return true;});
}

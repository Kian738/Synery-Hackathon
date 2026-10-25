import type {Message} from '../navigator/useNavigator';
/** An early delta must be visible even if a start notification is absent or delayed. */
export function startAssistantStream(all:Message[],streamId:string,model:string,id:()=>number):Message[]{
 const found=all.some(m=>m.role==='agent'&&m.streamId===streamId);
 return found?all.map(m=>m.role==='agent'&&m.streamId===streamId?{...m,model}:m):[...all,{id:id(),role:'agent',text:'',streamId,model,status:'streaming'}];
}
export function appendAssistantText(all:Message[],streamId:string,text:string,id:()=>number):Message[]{
 if(all.some(m=>m.role==='agent'&&m.streamId===streamId))return all.map(m=>m.role==='agent'&&m.streamId===streamId?{...m,text:m.text+text}:m);
 return [...all,{id:id(),role:'agent',text,streamId,status:'streaming'}];
}

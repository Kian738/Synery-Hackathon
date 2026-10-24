export interface LabelCandidate {id:string;x:number;y:number;width:number;height:number;priority:number}
/** Screen-space collision avoidance; a highlight is not permission to cover every room with text. */
export function placeMapLabels(candidates:LabelCandidate[],limit=28):Set<string>{
  const placed:LabelCandidate[]=[],ids=new Set<string>();
  for(const item of [...candidates].sort((a,b)=>b.priority-a.priority||a.id.localeCompare(b.id))){
    if(placed.length>=limit)break;
    if(placed.some(p=>Math.abs(p.x-item.x)<(p.width+item.width)/2+4&&Math.abs(p.y-item.y)<(p.height+item.height)/2+4))continue;
    placed.push(item);ids.add(item.id);
  }
  return ids;
}

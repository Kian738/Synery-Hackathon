import type { Route, RoutePoint } from "./types";

export interface PreviewSection {
  a: RoutePoint; b: RoutePoint; start: number; end: number; transition: boolean;
}
/** Time is simulated preview seconds, never a measured walking ETA. Gaps are chapters,
 * not traversable lines: the viewer changes landing without flying through the building. */
export function presentation(route: Route) {
  const sections: PreviewSection[] = [];
  const points = route.polyline.filter((p, i, all) => !i || p.gap || p.floor_id !== all[i-1].floor_id || Math.hypot(p.x-all[i-1].x,p.y-all[i-1].y)>1e-7);
  let duration = 0;
  for (let i=1;i<points.length;i++) {
    const a=points[i-1],b=points[i],transition=!!b.gap || a.floor_id!==b.floor_id;
    const seconds=transition ? 2 : Math.hypot(b.x-a.x,b.y-a.y)/1.2;
    sections.push({a,b,start:duration,end:duration+seconds,transition}); duration+=seconds;
  }
  let previous=0;
  const chapters=route.guide.steps.map((step,index)=>{
    let best=Infinity,time=previous;
    sections.forEach(s=>{for(const [p,t] of [[s.a,s.start],[s.b,s.end]] as const) {
      if(t+1e-7<previous || p.floor_id!==step.floor_id || !step.point)return;
      const d=Math.hypot(p.x-step.point[0],p.y-step.point[1]);if(d<best){best=d;time=t;}
    }});
    time=step.kind==="arrive"?duration:Math.min(duration,Math.max(time,index?previous+.001:0));
    previous=time;return time;
  });
  return {sections,duration,chapters,first:points[0]};
}
export type Presentation = ReturnType<typeof presentation>;
export function samplePreview(model: Presentation, seconds: number) {
  const time=Math.max(0,Math.min(seconds,model.duration));
  const section=model.sections.find(s=>time<s.end) ?? model.sections.at(-1);
  if(!section)return {point:model.first,heading:[0,1] as const,transition:false,step:0,arrived:true};
  const t=section.end===section.start?1:(time-section.start)/(section.end-section.start);
  const point=section.transition ? (t<.5?section.a:section.b) : {...section.a,x:section.a.x+(section.b.x-section.a.x)*t,y:section.a.y+(section.b.y-section.a.y)*t};
  const next=model.sections.find(s=>s.start>=section.end && !s.transition && s.a.floor_id===point.floor_id);
  const headingSection=section.transition?(next??section):section;
  let step=0;model.chapters.forEach((c,i)=>{if(c<=time+1e-7)step=i;});
  return {point,heading:[headingSection.b.x-headingSection.a.x,headingSection.b.y-headingSection.a.y] as const,transition:section.transition&&time<model.duration,step,arrived:time>=model.duration};
}
export function advancePreview(time:number,dt:number,speed:number,duration:number) {
  return Math.min(duration,Math.max(0,time+Math.max(0,dt)*speed));
}

/** Both renderers use the same walking sections. Never join across a hidden floor or gap. */
export function routeRuns(route:Route,visibleFloors:Set<string>):RoutePoint[][] {
  const runs:RoutePoint[][]=[];let run:RoutePoint[]=[];
  for(const section of presentation(route).sections){
    if(section.transition||!visibleFloors.has(section.a.floor_id)){if(run.length>1)runs.push(run);run=[];continue;}
    if(!run.length)run=[section.a];
    run.push(section.b);
  }
  if(run.length>1)runs.push(run);
  return runs;
}

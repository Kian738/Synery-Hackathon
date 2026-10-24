import type { Geometry, Opening } from "./types";

/** Align appearance to the nearest supplied wall; no assumed hinge/swing or invented leaf. */
export function openingFrame(geometry:Geometry, opening:Opening): {x:number;y:number;angle:number}|null {
  let best=Infinity,result:{x:number;y:number;angle:number}|null=null;
  for(const space of geometry.spaces.filter(s=>opening.space_ids.includes(s.id))) {
    space.polygon.forEach((a,i)=>{
      const b=space.polygon[(i+1)%space.polygon.length],dx=b[0]-a[0],dy=b[1]-a[1],length2=dx*dx+dy*dy;
      if(!length2)return;
      const t=Math.max(0,Math.min(1,((opening.position[0]-a[0])*dx+(opening.position[1]-a[1])*dy)/length2));
      const x=a[0]+t*dx,y=a[1]+t*dy,d=Math.hypot(x-opening.position[0],y-opening.position[1]);
      if(d<best){best=d;result={x,y,angle:Math.atan2(dy,dx)};}
    });
  }
  return best<=.8?result:null;
}

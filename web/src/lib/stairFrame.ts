import type {XY} from './types';
export interface StairFrame {cx:number;cy:number;ux:number;uy:number;length:number;width:number}
/** Orient the long axis towards the mapped upper landing; polygon vertex order is not an ascent direction. */
export function alignStairFrame(rect:StairFrame,lower:XY[],upper:XY[]):StairFrame&{orientationSource:string}{
 let r={...rect};if(r.ux< -1e-8||(Math.abs(r.ux)<1e-8&&r.uy<0)){r.ux=-r.ux;r.uy=-r.uy;}
 const project=(p:XY)=>(p[0]-r.cx)*r.ux+(p[1]-r.cy)*r.uy;
 const mean=(points:XY[])=>points.reduce((sum,p)=>sum+project(p),0)/points.length;
 const delta=lower.length&&upper.length?mean(upper)-mean(lower):upper.length?mean(upper):lower.length?-mean(lower):0;
 const known=Math.abs(delta)>Math.max(.2,r.length*.05);
 if(known&&delta<0){r.ux=-r.ux;r.uy=-r.uy;}
 return {...r,orientationSource:known?'mapped_landing_openings':'schematic_canonical_axis'};
}

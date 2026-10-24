import { test, expect } from "@playwright/test";
import { advancePreview, presentation, samplePreview, routeRuns } from "../src/lib/playback";
import type { Route } from "../src/lib/types";

const point=(x:number,y:number,floor_id="ground",gap=false)=>({x,y,floor_id,node:"",gap});
const route={polyline:[point(0,0),point(0,0),point(.05,0),point(2,0),point(2,3),point(20,20,"upper",true),point(24,20,"upper")],guide:{steps:[]}} as unknown as Route;
test("playback preserves distance across short edges at 30, 60 and 120 FPS",()=>{
  const model=presentation(route);
  const samples=[30,60,120].map(fps=>{let time=0;for(let i=0;i<fps*3;i++)time=advancePreview(time,1/fps,1,model.duration);return samplePreview(model,time).point!;});
  for(const p of samples){expect(p.x).toBeCloseTo(2,8);expect(p.y).toBeCloseTo(1.6,8);}
});
test("gaps change landing without interpolating through unsurveyed space",()=>{
  const model=presentation(route),gap=model.sections.find(s=>s.transition)!;
  expect(samplePreview(model,gap.start+.25).point!.x).toBe(2);
  expect(samplePreview(model,gap.end-.25).point!.x).toBe(20);
  expect(samplePreview(model,model.duration).arrived).toBe(true);
});
test("speed changes preserve position and elapsed overshoot",()=>{
  const model=presentation(route);let t=advancePreview(0,.5,1,model.duration);
  expect(samplePreview(model,t).point!.x).toBeCloseTo(.6);
  t=advancePreview(t,.5,2,model.duration);
  expect(samplePreview(model,t).point!.x).toBeCloseTo(1.8);
  expect(advancePreview(t,0,4,model.duration)).toBe(t);
});
test("renderers never join a hidden floor or connector gap",()=>{
  const current=routeRuns(route,new Set(["upper"]));
  expect(current).toHaveLength(1);
  expect(current[0].every(p=>p.floor_id==="upper")).toBe(true);
  expect(current[0].map(p=>p.x)).toEqual([20,24]);
  expect(routeRuns(route,new Set(["ground","upper"]))).toHaveLength(2);
});

import type { Route } from "../lib/types";
import type { Presentation } from "../lib/playback";
import { Pictogram } from "./Pictogram";

const clock=(s:number)=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`;
export function GuidePlayer({route,model,time,playing,speed,step,reduced,transition,onSeek,onPlay,onPrevious,onNext,onSpeed,onRepeat,onExit}:{
  route:Route;model:Presentation;time:number;playing:boolean;speed:number;step:number;reduced:boolean;transition:string|null;
  onSeek:(v:number)=>void;onPlay:()=>void;onPrevious:()=>void;onNext:()=>void;onSpeed:(v:number)=>void;onRepeat?:()=>void;onExit?:()=>void;
}) {
  const safeTime=Math.max(0,Math.min(Number.isFinite(time)?time:0,model.duration));
  const arrived=safeTime>=model.duration-.011,progress=model.duration?100*safeTime/model.duration:100;
  const steps=route.guide.steps, last=steps.length-1;
  // The card shows what is AHEAD: the next action and how far away it is, counting down while the preview walks. The step list's first entry
  // ("You are here") is where the walk starts, so the first action is step 1.
  const upcomingIndex=Math.min(step+1,last), upcoming=steps[upcomingIndex], after=steps[upcomingIndex+1];
  const t0=model.chapters[Math.min(step,upcomingIndex)]??0, t1=model.chapters[upcomingIndex]??model.duration;
  const share=t1>t0?Math.max(0,Math.min(1,(t1-safeTime)/(t1-t0))):0;
  const remaining=arrived?0:Math.round((upcoming?.metres??0)*share);
  const lower=(x?:string)=>x?`${x.charAt(0).toLowerCase()}${x.slice(1)}`:"";
  return <section className="guide-player" aria-label="Route preview player">
    <div className="player-instruction k-guide-now" role="status" aria-live="polite" data-kind={upcoming?.kind}>
      <span className="k-guide-icon"><Pictogram name={upcoming?.icon??"straight"} size={30}/></span>
      <div className="k-guide-body">
        <span className="k-guide-count">{arrived?"Finished":`Step ${upcomingIndex} of ${last}`}</span>
        <strong>{arrived?"You have arrived":upcoming?.headline||upcoming?.text}</strong>
        <span className="k-guide-target">{transition??(arrived?upcoming?.target:upcoming?.target)}</span>
        {arrived&&<span className="k-guide-hint">Drag the view to look around</span>}
        {after&&!arrived&&<span className="k-guide-next">After that: {after.headline?`${lower(after.headline)} ${after.target??""}`.trim():after.short}</span>}
      </div>
      {!arrived&&<b className="k-guide-meter" aria-label={remaining>=3?`${remaining} metres to go`:"now"}>{remaining>=3?<><i>{remaining}</i><u>m</u></>:<i className="now">now</i>}</b>}
      <button aria-label="Repeat instruction" title="Repeat instruction" onClick={onRepeat}><Pictogram name="speaker"/></button>
    </div>
    <div className="player-progress">
      <div className="progress-track"><span style={{width:`${progress}%`}}/><i style={{left:`${progress}%`}}/></div>
      <input type="range" aria-label="Preview progress" aria-valuetext={`${clock(time)} of ${clock(model.duration)}, decision ${step+1}`} min={0} max={Math.ceil(model.duration*100)/100||1} step="0.01" value={time} onChange={e=>onSeek(Number(e.target.value))}/>
      <div className="progress-chapters">{model.chapters.map((c,i)=><button key={i} title={route.guide.steps[i]?.short} aria-label={`Seek to decision ${i+1}: ${route.guide.steps[i]?.short??''}`} style={{left:`${100*c/(model.duration||1)}%`}} onClick={()=>onSeek(c)}><i data-floor={route.guide.steps[i]?.kind==='floor'}/></button>)}</div>
    </div>
    <div className="player-transport">
      <span className="player-time">{clock(time)} <span>/ {clock(model.duration)}</span></span>
      <div className="player-main-controls"><button aria-label="Previous instruction" title="Previous instruction" disabled={step<=0} onClick={onPrevious}><Pictogram name="skip-back"/></button>
        {!reduced&&<button className="play-toggle" aria-label={arrived?"Replay preview":playing?"Pause preview":"Play preview"} title={arrived?"Replay":"Play / pause (Space)"} onClick={onPlay}><Pictogram name={arrived?"replay":playing?"pause":"play"} size={25}/></button>}
        <button aria-label="Next instruction" title="Next instruction" disabled={arrived} onClick={onNext}><Pictogram name="skip-next"/></button></div>
      <div className="player-options"><div role="group" aria-label="Playback speed" className="speed-options">{[.5,1,2,4].map(v=><button key={v} aria-label={`Playback speed ${v}×`} aria-pressed={speed===v} onClick={()=>onSpeed(v)}>{v}×</button>)}</div>{arrived&&<button aria-label="Finish preview" onClick={onExit}>Finish</button>}</div>
    </div>
  </section>;
}

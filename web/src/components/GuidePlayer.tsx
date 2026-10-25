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
  const instruction=route.guide.steps[step],next=route.guide.steps[step+1];
  return <section className="guide-player" aria-label="Route preview player">
    <div className="player-instruction k-guide-now" role="status" aria-live="polite" data-kind={instruction?.kind}>
      <span className="k-guide-icon"><Pictogram name={instruction?.icon??"straight"} size={30}/></span>
      <div className="k-guide-body">
        <small>{arrived?"You have arrived":transition??`Step ${step+1} of ${route.guide.steps.length}`}</small>
        <strong>{instruction?.headline||instruction?.text}</strong>
        {instruction?.headline&&<span className="k-guide-target">{instruction.target}</span>}
        {next&&!arrived&&<em className="k-guide-next">Then: {next.headline?`${next.headline.charAt(0).toLowerCase()}${next.headline.slice(1)} ${next.target}`:next.short}</em>}
      </div>
      {instruction?.cue&&instruction.cue!=="now"&&!arrived&&<b className="k-guide-cue">{instruction.cue}</b>}
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

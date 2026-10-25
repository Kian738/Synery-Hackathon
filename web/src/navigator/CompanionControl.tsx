import { useEffect } from "react";
import {createPortal} from "react-dom";
import { LaptopPairing, routeStateFromGuide, useCompanionHost } from "../companion";
import { Pictogram } from "../components/Pictogram";
import type { GuideStep } from "../lib/types";

/** Pairing is independent of building/session identity. A phone can request UI actions,
 * never update declared location or analytical route state. Closing the panel keeps it paired. */
export function CompanionControl({path,steps,index,routeId,buildingId,open,onToggle,onStep,onLook,onRecenter}:{
  path?:[number,number][];steps:GuideStep[];index:number;routeId?:string;buildingId:string;open:boolean;onToggle:()=>void;
  onStep:(action:"next"|"back"|"repeat")=>void;onLook:(yaw:number,pitch:number)=>void;onRecenter:()=>void;
}) {
  const host=useCompanionHost({onStep,onHeading:onLook,onRecenter});
  const publish=host.publish;
  useEffect(()=>{publish({...routeStateFromGuide(steps,index,{routeId,path}),building_id:buildingId});},[publish,steps,index,routeId,buildingId,path]);
  return <>
    <button aria-label="Phone companion" aria-expanded={open} aria-pressed={host.phoneOnline} title={host.phoneOnline?"Phone connected":"Use a phone with this laptop"} onClick={onToggle}><Pictogram name="phone" size={18}/><span>Phone</span></button>
    {open&&createPortal(<section className="companion-drawer" role="dialog" aria-label="Phone companion setup">
      <button className="companion-close" aria-label="Close phone setup" onClick={onToggle}><Pictogram name="close"/></button>
      <LaptopPairing host={host}/>
      <p className="companion-setup-hint">Start the app with <code>uv run fw start --lan</code> to connect from the same network. Touch works over HTTP; motion look requires HTTPS on the phone.</p>
    </section>,document.body)}
  </>;
}

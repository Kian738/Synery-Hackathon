import { useEffect, useMemo, useState } from "react";
import { PlanView } from "./PlanView";
import { api } from "../lib/api";
import type { Geometry } from "../lib/types";

export function BuildDialog({onClose,onBuilt}:{onClose:()=>void;onBuilt:(id:string)=>void}) {
  const [files,setFiles]=useState<File[]>([]),[levels,setLevels]=useState("0"),[width,setWidth]=useState("40"),[name,setName]=useState("Imported building");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[draft,setDraft]=useState<{id:string;geometry:Geometry;report:unknown}|null>(null);
  const [overlay,setOverlay]=useState(true);
  const url=useMemo(()=>files.length?URL.createObjectURL(files[0]):"",[files]);
  useEffect(()=>()=>{if(url)URL.revokeObjectURL(url);},[url]);
  const build=async()=>{
    setBusy(true);setError("");
    try {
      const form=new FormData();files.forEach(f=>form.append("files",f));
      form.set("levels",levels);form.set("width_m",width);form.set("name",name);form.set("vision","false");
      const response=await fetch("/api/build",{method:"POST",body:form});
      const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==="string"?result.detail:"The plan could not be imported.");
      const geometry=await api.geometry(result.building_id);setDraft({id:result.building_id,geometry,report:result.report});
    } catch(e){setError(String(e));}finally{setBusy(false);}
  };
  return <div className="import-backdrop"><section role="dialog" aria-modal="true" aria-label="Import floor plans" className="import-dialog">
    <header><h2>{draft?"Review the reconstructed draft":"Give the building a floor plan"}</h2><button onClick={onClose} aria-label="Close import">×</button></header>
    {!draft?<><p>Upload PNG floor plans and supply the real width of the first plan. Reconstructed doors and labels require review.</p>
      <label>Building name<input value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>Floor-plan images<input type="file" accept="image/png" multiple onChange={e=>{const selected=Array.from(e.target.files??[]);setFiles(selected);setLevels(selected.map((_,i)=>i).join(","));}}/></label>
      <div className="import-fields"><label>Floor levels, in file order<input value={levels} onChange={e=>setLevels(e.target.value)}/></label>
      <label>First plan width (metres)<input type="number" min="1" max="2000" value={width} onChange={e=>setWidth(e.target.value)}/></label></div>
      {url&&<img className="source-preview" src={url} alt="Source floor plan"/>}
      <button className="primary-action" disabled={busy||!files.length||Number(width)<=0} onClick={build}>{busy?"Reconstructing the draft...":"Build draft"}</button>
    </>:<><p>This is an inferred draft. Check scale, doors and connectivity before using it for guidance.</p>
      <button onClick={()=>setOverlay(!overlay)} aria-pressed={overlay}>Source image overlay</button>
      <div className="draft-preview"><PlanView geometry={draft.geometry} floorId={draft.geometry.floors[0].id}/>
        {overlay&&url&&<img src={url} alt="Source overlay for visual comparison; plan margins may differ"/>}</div>
      <p>Overlay is a visual reference; image margins may differ. Inferred openings remain marked in the model.</p>
      <button className="primary-action" onClick={()=>onBuilt(draft.id)}>Confirm draft and explore</button>
    </>}
    {error&&<p role="alert">{error}</p>}
  </section></div>;
}

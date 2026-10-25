import {useEffect,useRef,useState} from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

interface Context {bounds:[[number,number],[number,number]];center:[number,number];outline:any;recorded_height_m:number|null;source_url:string;alignment:string}
export default function ExteriorView({buildingId,onEnter}:{buildingId:string;onEnter:()=>void}){
  const host=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null);
  const [context,setContext]=useState<Context|null>(null),[error,setError]=useState(''),[tilesFailed,setTilesFailed]=useState(false),[retry,setRetry]=useState(0),[entering,setEntering]=useState(false),[notice,setNotice]=useState('');
  useEffect(()=>{const abort=new AbortController();setContext(null);setError('');setTilesFailed(false);
    fetch(`/api/buildings/${encodeURIComponent(buildingId)}/exterior`,{signal:abort.signal}).then(async r=>{const body=await r.json();if(!r.ok)throw Error(body.detail??'Exterior unavailable');return body;}).then(setContext).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();
  },[buildingId,retry]);
  useEffect(()=>{
    if(!context||!host.current)return;
    const m=new maplibregl.Map({container:host.current,center:context.center,zoom:16,pitch:38,
      attributionControl:false,style:{version:8,sources:{osm:{type:'raster',tiles:[import.meta.env.VITE_MAP_TILE_URL??'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'background',type:'background',paint:{'background-color':'#dfe5df'}},{id:'surroundings',type:'raster',source:'osm'}]}});
    map.current=m;m.addControl(new maplibregl.AttributionControl({compact:false}),'bottom-right');m.addControl(new maplibregl.NavigationControl(),'bottom-right');m.addControl(new maplibregl.ScaleControl(),'bottom-left');
    m.on('error',()=>setTilesFailed(true));
    m.on('load',()=>{m.addSource('building',{type:'geojson',data:context.outline});m.addLayer({id:'building-outline',type:'line',source:'building',paint:{'line-color':'#1e7a4c','line-width':3}});
      m.addLayer(context.recorded_height_m?{id:'building-fill',type:'fill-extrusion',source:'building',paint:{'fill-extrusion-color':'#758d85','fill-extrusion-height':context.recorded_height_m,'fill-extrusion-opacity':.8}}:{id:'building-fill',type:'fill',source:'building',paint:{'fill-color':'#1e7a4c','fill-opacity':.15}});
      m.fitBounds(context.bounds,{padding:70,maxZoom:18,duration:0});});
    return()=>{m.remove();map.current=null;};
  },[context]);
  useEffect(()=>{if(!entering)return;const timer=setTimeout(onEnter,matchMedia('(prefers-reduced-motion: reduce)').matches?0:650);return()=>clearTimeout(timer);},[entering,onEnter]);
  const enter=()=>{if(context)map.current?.fitBounds(context.bounds,{padding:20,maxZoom:20,duration:600});setEntering(true);};
  return <section className={`exterior-view ${entering?'entering':''}`} aria-label="Mapped exterior">
    <div ref={host} className="exterior-map"/>
    <div className="exterior-caption"><strong>Outside → inside</strong><p>{context?'Mapped surroundings from OpenStreetMap':'Loading the recorded geographic source…'}</p>
      {error&&<p role="alert">{error}<button onClick={()=>setRetry(n=>n+1)}>Retry map</button></p>}
      {tilesFailed&&<p role="status">Some map tiles are unavailable. The recorded outline and indoor model remain available.</p>}
      <button className="enter-building" onClick={context?enter:onEnter} disabled={entering}>{entering?'Entering…':'Explore inside'}</button>
      {context&&<><div className="exterior-actions"><button onClick={()=>map.current?.fitBounds(context.bounds,{padding:80,maxZoom:18,duration:500})}>Building</button><button onClick={()=>map.current?.easeTo({center:context.center,zoom:14,pitch:0,duration:600})}>Surroundings</button><a href={context.source_url} target="_blank" rel="noreferrer">Source ↗</a></div><details><summary>Map alignment and data</summary><p>{context.alignment}</p><p>{context.recorded_height_m?`Recorded exterior height: ${context.recorded_height_m} m.`:'No surveyed exterior height is supplied; the outline is shown without an invented height.'}</p></details></>}
      {notice&&<p role="status">{notice}</p>}
    </div>
  </section>;
}

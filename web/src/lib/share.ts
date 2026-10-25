export function roomLink(building:string,room:string,origin?:string|null,stepFree=false){
  const url=new URL('/',location.origin);url.searchParams.set('building',building);
  url.searchParams.set('room',room);if(origin)url.searchParams.set('at',origin);
  if(stepFree)url.searchParams.set('step_free','1');return url.href;
}
export async function copyText(text:string){
  if(!navigator.clipboard?.writeText)throw Error('Clipboard is unavailable here. Use a secure browser context.');
  await navigator.clipboard.writeText(text);
}
export function downloadCsv(name:string,rows:unknown[][]){
  const csv=rows.map(row=>row.map(value=>{let s=String(value??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob(['\uFEFF',csv],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function readLocal<T>(key:string,fallback:T):T{try{return JSON.parse(localStorage.getItem(key)??'null')??fallback;}catch{return fallback;}}
export function saveLocal(key:string,value:unknown){try{localStorage.setItem(key,JSON.stringify(value));return true;}catch{return false;}}

import {useEffect,useRef,type RefObject} from 'react';
export function useDialogFocus(ref:RefObject<HTMLElement|null>,onClose:()=>void){
  const close=useRef(onClose);close.current=onClose;
  useEffect(()=>{const before=document.activeElement as HTMLElement|null;const node=ref.current;if(!node)return;
    const items=()=>[...node.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,a[href],[tabindex="0"]')].filter(n=>n.getClientRects().length);
    (node.querySelector<HTMLElement>("input")??items()[0]??node).focus();
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close.current();}if(e.key==='Tab'){const all=items(),first=all[0],last=all.at(-1);if(!first){e.preventDefault();node.focus();}else if(e.shiftKey&&(document.activeElement===first||document.activeElement===node)){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
    node.addEventListener('keydown',key);return()=>{node.removeEventListener('keydown',key);if(before?.isConnected&&before.getClientRects().length)before.focus();else document.querySelector<HTMLElement>('[aria-label="Building tools"]')?.focus();};
  },[ref]);
}

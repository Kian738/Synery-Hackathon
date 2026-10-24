import {useEffect,useState} from "react";
import {toDataURL} from "qrcode";

/** The pairing URL stays local. No QR generation service sees the one-use code. */
export function PairingQR({url}:{url:string}){
  const [image,setImage]=useState("");const [failed,setFailed]=useState(false);
  useEffect(()=>{let current=true;setImage("");setFailed(false);
    toDataURL(url,{width:228,margin:4,errorCorrectionLevel:"M",color:{dark:"#10171cff",light:"#ffffffff"}}).then(value=>{if(current)setImage(value);}).catch(()=>{if(current)setFailed(true);});
    return()=>{current=false;};
  },[url]);
  return image?<img className="pairing-qr" src={image} width={228} height={228} alt="Scan to pair your phone"/>:failed?<p role="status">QR unavailable. Use the address and code below.</p>:<div className="pairing-qr-placeholder" aria-label="Preparing pairing QR"/>;
}

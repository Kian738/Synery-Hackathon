import {useMemo} from 'react';
import {RoomText} from './RoomText';
import {answerBlocks} from '../lib/answerFormat';
import type {Space} from '../lib/types';
export function AgentReply({text,spaces,onRoom}:{text:string;spaces:Space[];onRoom:(id:string)=>void}){
  const blocks=useMemo(()=>answerBlocks(text),[text]);
  const inline=(value:string)=><RoomText text={value} spaces={spaces} onRoom={onRoom}/>;
  return <div className="agent-reply">{blocks.map((block,i)=>block.kind==='ul'?<ul key={i}>{block.lines.map((line,j)=><li key={j}>{inline(line)}</li>)}</ul>:block.kind==='ol'?<ol key={i} start={block.ordinals?.[0]}>{block.lines.map((line,j)=><li key={j} value={block.ordinals?.[j]}>{inline(line)}</li>)}</ol>:block.kind==='heading'?<h4 key={i}>{inline(block.lines[0])}</h4>:<p key={i}>{inline(block.lines.join(' '))}</p>)}</div>;
}

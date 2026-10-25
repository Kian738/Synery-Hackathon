export type AnswerBlock={kind:'paragraph'|'heading'|'ul'|'ol';lines:string[];ordinals?:number[]};
/** Format only: every nonempty content line survives, including partial streamed text. */
export function answerBlocks(text:string):AnswerBlock[]{
  const blocks:AnswerBlock[]=[];let current:AnswerBlock|undefined;
  for(const raw of text.split(/\r?\n/)){
    const line=raw.trim();if(!line){current=undefined;continue;}
    const bullet=line.match(/^[-*\u2022]\s+(.+)/),number=line.match(/^\d+[.)]\s+(.+)/),heading=line.match(/^#{1,3}\s+(.+)/);
    const kind=bullet?'ul':number?'ol':heading?'heading':'paragraph';
    const content=(bullet??number??heading)?.[1]??line;
    if(current?.kind===kind&&kind!=='heading'){current.lines.push(content);if(number)current.ordinals!.push(parseInt(line,10));}
    else{current={kind,lines:[content],...(number?{ordinals:[parseInt(line,10)]}:{})};blocks.push(current);}
  }
  return blocks;
}

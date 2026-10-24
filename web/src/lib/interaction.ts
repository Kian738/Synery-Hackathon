/** Selection is a tap/click, never a camera gesture—even if a drag returns to its start. */
export class PickIntent {
  private start:[number,number]=[0,0];
  moved=false;
  begin(x:number,y:number){this.start=[x,y];this.moved=false;}
  move(x:number,y:number){if(Math.hypot(x-this.start[0],y-this.start[1])>5)this.moved=true;}
  cancel(){this.moved=true;}
}

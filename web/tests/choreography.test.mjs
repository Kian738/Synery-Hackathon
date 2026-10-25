import assert from 'node:assert/strict';
import {stageFor} from '../src/lib/choreography.ts';
const look={name:id=>`N(${id})`,floorOf:()=>'F0'};
const impact={cut_off_ids:['r1','r2'],shorter_way_out_count:2,cut_off_count:2,longer_way_out_count:0,rooms_cut_off_from_exits:[],rooms_reconnected:[],most_affected:[]};
const route={stops:['a','b'],length_m:84,walk_m:84,steps:[],constraints:[],floors:['F0'],polyline:[{floor_id:'F0',x:0,y:0,node:'a'}],guide:{steps:[],spoken:''}};
const door={id:'d',floor_id:'F0',space_ids:['a','b'],kind:'door',position:[0,0],width_m:1,step_free:true};
const cases={
  route:{type:'route',route},
  visual_result:{type:'visual_result',total_rows:2,result:{id:'x',kind:'matches',title:'2 printers',entities:[{id:'p1',floor_id:'F0',kind:'asset'},{id:'p2',floor_id:'F0',kind:'asset'}],floor_ids:['F0'],measurements:{},lines:[],warnings:[],provenance:'p'}},
  highlight:{type:'highlight',ids:['a']},
  closure:{type:'closure',id:'lift',closed:true,impact},
  preview_door:{type:'preview_door',door,impact},
  fix_preview:{type:'fix_preview',opening:door,fix:{reachable_before:false,reason:'r',verified:true,widen:[]},start:'a',destination:'b'},
  edit:{type:'edit',op:'add_door',door},
  weak_points:{type:'weak_points',items:[{name:'L',element_ids:[],room_ids:['r1'],rooms_lost:1,of_rooms:2,kind:'lift'}],profile:'step-free'},
  scenario_result:{type:'scenario_result',hazard:'h',report:{steps:[],abstained:null,answer:null,findings:[]}},
  scenario_replay:{type:'scenario_replay',action:'play'},
  profile:{type:'profile',profile:{step_free:true,min_door_width_m:null,location:null}},
  choice:{type:'choice',question:'Which?',options:['A','B']},
};
for(const [kind,e] of Object.entries(cases)){const s=stageFor(e,look);assert.equal(s.kind,kind);assert.ok(s.card.headline.length>0,kind);}
assert.equal(stageFor(cases.route,look).line,'draw');
assert.equal(stageFor(cases.route,look).card.headline,'N(b): 84 m, about 1 min');
assert.deepEqual(stageFor(cases.visual_result,look).numbered,[{id:'p1',n:1},{id:'p2',n:2}]);
const c=stageFor(cases.closure,look);assert.deepEqual(c.danger,['lift']);assert.deepEqual(c.affected,['r1','r2']);assert.match(c.card.headline,/2 rooms lose/);
assert.deepEqual(stageFor(cases.edit,look).door,{id:'d',tone:'added'});
assert.equal(stageFor({type:'edit',op:'undo',undone:'add_door'},look).door,null);
console.log('choreography: every UiEvent type maps to a stage');

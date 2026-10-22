import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';
const source=await readFile(new URL('../../src/shiliu/static/ask-research.js',import.meta.url),'utf8');
class Node {
  constructor(){this.children=[];this.dataset={};this.textContent='';this.hidden=false;this.open=false;this.nodes=new Map();}
  querySelector(key){if(!this.nodes.has(key))this.nodes.set(key,new Node());return this.nodes.get(key);}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this[key]=value;}
}
const setup=()=>{const window={};const root=new Node();vm.runInNewContext(source,{window,document:{createElement:()=>new Node()}});
  const api=window.ShiliuAskResearch.create(root);const panel=root.querySelector('[data-deep-research]');api.reset('deep','r');
  let seq=0;const event=(phase,payload={},source_id='r',sequence=++seq)=>api.event({source_id,sequence,event_type:'deep_research',payload:{phase,round:1,...payload}});
  return {api,panel,event,title:panel.querySelector('[data-research-current]'),list:panel.querySelector('[data-research-tasks]')};};
const tasks=[{task_id:'1:0',kind:'search_transcripts',label:'东京 美食'},{task_id:'1:1',kind:'search_transcripts',label:'大阪 美食'}];
const itemStatus=(row,index)=>row.children[2].children[index].dataset.status;
const stepLabel=row=>row.children[1].children[0].textContent;

test('only actual steps append, parallel tasks share a step and completion remains independent',()=>{
  const {api,panel,event,list}=setup();event('controller_started',{attempt:1});assert.equal(list.children.length,1);
  event('controller_completed');const controller=list.children[0];
  event('batch_started',{tasks});event('tool_started',{task_id:'1:0'});event('tool_started',{task_id:'1:1'});
  const search=list.children[1];assert.equal(stepLabel(search),'同时检索 2 条线索');
  event('tool_completed',{task_id:'1:1',status:'ok'});assert.equal(controller,list.children[0]);
  assert.equal(itemStatus(search,0),'searching');assert.equal(itemStatus(search,1),'found');
  event('tool_completed',{task_id:'1:0',status:'ok'});assert.equal(search.dataset.status,'done');
  event('reduce_started',{task_id:'1:0'});event('reduce_started',{task_id:'1:1'});
  const reduce=list.children[2];event('reduce_completed',{task_id:'1:0',status:'ok'});
  assert.equal(itemStatus(reduce,0),'done');assert.equal(itemStatus(reduce,1),'reducing');
  assert.equal(reduce.dataset.status,'active');assert.equal(list.children.length,3);
  api.answerStarted();assert.equal(panel.open,false);panel.open=true;api.answerStarted();assert.equal(panel.open,true);
});
test('old runs, repeated and out of order events cannot regress or duplicate steps',()=>{
  const {event,list,title}=setup();event('batch_started',{tasks});event('tool_started',{task_id:'1:0'},'r',5);
  event('tool_completed',{task_id:'1:0',status:'ok'},'r',4);event('tool_completed',{task_id:'1:0',status:'ok'},'other',6);
  assert.equal(itemStatus(list.children[0],0),'searching');event('tool_completed',{task_id:'1:0',status:'ok'},'r',6);
  event('tool_started',{task_id:'1:0'},'r',6);assert.equal(itemStatus(list.children[0],0),'found');
  event('batch_started',{tasks},'r',6);assert.equal(list.children.length,1);assert.doesNotMatch(title.textContent,/成功|充分/);
});
test('long research retains every step in chronological order without separate early history or round labels',()=>{
  const {event,list,panel}=setup();for(let round=1;round<=10;round++){
    event('controller_started',{round,attempt:1});event('controller_completed',{round});
    event('batch_started',{round,tasks});event('tool_completed',{round,task_id:'1:0',status:'ok'});
    event('tool_completed',{round,task_id:'1:1',status:'ok'});event('batch_completed',{round});}
  assert.equal(list.children.length,20);
  assert.equal(stepLabel(list.children[0]),'确定检索方向');assert.equal(stepLabel(list.children[18]),'判断是否需要补充资料');
  assert.equal(stepLabel(list.children[19]),'同时检索 2 条线索');
  assert.equal(panel.querySelector('[data-research-meta]').textContent,'');
  assert.doesNotMatch(source,/research-history|research-records|第 .*轮/);
});
test('empty retrieval, empty Reduce and a Controller retry do not claim success',()=>{
  const {event,list}=setup();event('controller_started',{attempt:1});event('controller_started',{attempt:2});
  assert.equal(list.children[0].dataset.status,'warning');event('controller_completed');
  event('batch_started',{tasks});event('tool_completed',{task_id:'1:0',status:'empty'});
  event('tool_completed',{task_id:'1:1',status:'ok'});event('reduce_started',{task_id:'1:1'});
  event('reduce_completed',{task_id:'1:1',status:'empty'});event('batch_completed');
  assert.equal(itemStatus(list.children[2],0),'empty');assert.equal(itemStatus(list.children[3],0),'unresolved');
  assert.equal(list.children[2].dataset.status,'warning');assert.equal(list.children[3].dataset.status,'warning');
});
test('timeout, insufficiency, network failure and a new Fast question end or clear activity',()=>{
  const {event,api,panel,list}=setup();event('batch_started',{tasks});event('tool_started',{task_id:'1:0'});
  event('research_finished',{reason:'timeout'});assert.match(panel.querySelector('[data-research-note]').textContent,/时间上限/);
  api.fail();assert.equal(panel.open,false);assert.equal(list.children[0].dataset.status,'warning');
  const before=itemStatus(list.children[0],0);event('tool_started',{task_id:'1:0'});assert.equal(itemStatus(list.children[0],0),before);
  api.reset('deep','new');assert.equal(list.children.length,0);assert.equal(panel.open,true);
  api.finish({status:'insufficient'});assert.equal(panel.open,false);assert.match(panel.querySelector('[data-research-note]').textContent,/未形成/);
  api.reset('fast');assert.equal(panel.hidden,true);assert.equal(list.children.length,0);
});
test('Final remains expanded until actual body, manual reopening survives later parts and terminal result',()=>{
  const {api,panel,event,title,list}=setup();event('batch_started',{tasks});
  api.event({source_id:'r',sequence:50,event_type:'answer_generation_started',payload:{}});
  assert.equal(title.textContent,'正在生成回答');assert.equal(panel.open,true);assert.equal(stepLabel(list.children[1]),'生成回答');
  api.answerStarted();assert.equal(title.textContent,'回答正在展开');assert.equal(panel.open,false);
  panel.open=true;api.answerStarted();api.finish({status:'partial'});assert.equal(panel.open,true);
  event('controller_started',{},'r',99);assert.equal(title.textContent,'研究记录');assert.equal(list.children.length,2);
});
test('model labels remain text and no hidden reasoning or timers manufacture progress',()=>{
  const {event,list}=setup();event('batch_started',{tasks:[{task_id:'1:0',kind:'read_context',label:'<script>bad</script>'}]});
  assert.equal(list.children[0].children[2].children[0].children[0].textContent,'<script>bad</script>');
  assert.doesNotMatch(source,/innerHTML|reasoning_content|messages|setInterval/);
});


test('Jev only changes the existing reduction step after actual dispatch and clears on next run',()=>{
  const {api,event,list,title}=setup();
  event('batch_started',{tasks});event('reduce_started',{task_id:'1:0'});
  assert.equal(stepLabel(list.children[1]),'整理检索到的资料');
  event('jev_started');assert.match(title.textContent,/Jev/);
  assert.equal(list.children.length,2);assert.match(stepLabel(list.children[1]),/Jev/);
  event('reduce_started',{task_id:'1:1'});assert.equal(list.children.length,2);
  event('batch_completed');event('controller_started',{round:2,attempt:1});
  assert.doesNotMatch(title.textContent,/Jev/);
  api.reset('deep','s-run');event('batch_started',{tasks},'s-run',1);
  event('reduce_started',{task_id:'1:0'},'s-run',2);
  assert.doesNotMatch(stepLabel(list.children[1]),/Jev/);
});

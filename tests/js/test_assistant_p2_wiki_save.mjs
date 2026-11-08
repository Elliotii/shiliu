import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

class Element {
  constructor(){this.children=[];this.dataset={};this.textContent='';this.title='';}
  append(...nodes){this.children.push(...nodes);}
  after(node){this.afterNode=node;}
  replaceChildren(){this.children=[];}
  setAttribute(){}
  get childNodes(){return this.children;}
}
async function fixture(){
  const source=await readFile('src/shiliu/static/assistant.js','utf8');
  const code=source.slice(source.indexOf('  let wikiSavePolling ='),source.indexOf('  async function loadMemories()'));
  const nodes=new Map(), pending=[];
  const $=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  const state={threadId:'old',spaceId:1,navigationSerial:0,navigationPending:false,runId:null};
  const context={state,$,document:{createElement:()=>new Element(),createTextNode:text=>({textContent:text})},setInterval:()=>{},
    navigationCurrent:(serial,space)=>serial===state.navigationSerial && space===state.spaceId,
    api:path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject})),openDrawer(){},openKnowledgePage(){},toast(){}};
  vm.createContext(context);vm.runInContext(code+'\nthis.run={refreshWikiSaves,get polling(){return wikiSavePolling},node:wikiSaveState};',context);
  return {...context,pending,run:context.run};
}
test('late empty response cannot erase an accepted save or stop polling',async()=>{
  const {run,pending,state}=await fixture();
  const old=run.refreshWikiSaves(),fresh=run.refreshWikiSaves();
  pending[1].resolve({jobs:[{id:'job',status:'queued',pages:[]}]});await fresh;
  pending[0].resolve({jobs:[]});await old;
  assert.equal(run.node.children.length,1);assert.equal(run.polling,true);assert.equal(state.runId,null);
});
test('navigation excludes old task results; completed state stops polling',async()=>{
  const {run,pending,state}=await fixture();
  const old=run.refreshWikiSaves();state.navigationSerial++;state.threadId='new';
  pending[0].resolve({jobs:[{id:'old',status:'processing'}]});await old;
  assert.equal(run.node.children.length,0);
  const current=run.refreshWikiSaves();pending[1].resolve({jobs:[{id:'new',status:'completed',pages:[]}]});await current;
  assert.equal(run.polling,false);assert.equal(run.node.children[0].dataset.jobId,'new');
});

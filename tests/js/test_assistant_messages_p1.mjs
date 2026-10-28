import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.dataset={};this._text='';this.isConnected=true;this.scrollTop=0;this.attributes={};}
  set textContent(value){this._text=value;this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...items){items.forEach(item=>{item.parentElement=this;this.children.push(item);});}
  replaceChildren(...items){this._text='';this.children=[];this.append(...items);}
  setAttribute(key,value){this.attributes[key]=value;}
  focus(options){this.focused=options || true;}
  querySelectorAll(tag){return this.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...child.querySelectorAll(tag)]);}
  querySelector(tag){return this.querySelectorAll(tag)[0];}
}
async function fixture(){
  const source=await readFile('src/shiliu/static/assistant.js','utf8');
  const code=source.slice(source.indexOf('  const messages ='),source.indexOf('  function showFatal('));
  const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  $('assistant-message-view').value='all';
  const pending=[];
  const context={URLSearchParams,Map,Date,Option:Element,document:{createElement:tag=>new Element(tag)},$,state:{spaces:[]},api:(path)=>{
    if(path==='/messages/unread-count')return Promise.resolve({unread_count:0});
    return new Promise((resolve,reject)=>pending.push({path,resolve,reject}));
  }};
  vm.createContext(context);vm.runInContext(code+'\nthis.run={loadMessages,messages,openMessage,backToMessages,showMessage};',context);
  return {$,pending,run:context.run};
}

test('filter response ownership and pagination stay bound to current query',async()=>{
  const {$,pending,run}=await fixture();
  const old=run.loadMessages();const oldRequest=pending.shift();
  run.messages.cursor='old-cursor';$('assistant-message-more').hidden=false;
  $('assistant-message-view').value='pending';
  const current=run.loadMessages();const currentRequest=pending.shift();
  assert.equal($('assistant-message-more').hidden,true);
  assert.equal($('assistant-message-more').disabled,true);
  assert.equal(run.messages.cursor,null);
  assert.match(currentRequest.path,/view=pending/);assert(!currentRequest.path.includes('cursor='));
  currentRequest.resolve({items:[],next_cursor:'new-cursor'});await current;
  oldRequest.resolve({items:[{id:'stale'}],next_cursor:'old-cursor'});await old;
  assert.equal(run.messages.cursor,'new-cursor');
  assert.equal($('assistant-message-list').children.length,0);
  assert.equal($('assistant-message-list').textContent,'此筛选下暂无消息。');
});

test('refresh failure retains existing list, current scope and error feedback',async()=>{
  const {$,pending,run}=await fixture();
  const original=new Element();original.textContent='existing result';$('assistant-message-list').append(original);
  $('assistant-message-space_id').value='12';
  const request=run.loadMessages();const entry=pending.shift();
  assert.match(entry.path,/space_id=12/);
  entry.reject(new Error('offline'));await request;
  assert.equal($('assistant-message-list').children[0],original);
  assert.match($('assistant-message-error').textContent,/offline/);
  assert.equal($('assistant-message-space_id').value,'12');
});

const sample=(id='m')=>({id,object_label:'视频正文修改建议',change_summary:'一项正文增补',business_state:'pending',source_type:'video',activity_at:'2026-10-28T10:25:00+08:00',links:[],actions:[],source_times:[],processing_times:[]});
test('history stays visible when filters collapse and failed query cannot reuse cursor',async()=>{
  const {$,pending,run}=await fixture();$('assistant-message-show_history').checked=true;
  const first=run.loadMessages();pending.shift().resolve({items:[sample()],next_cursor:'page2'});await first;
  $('assistant-message-secondary').hidden=true;
  assert.match($('assistant-message-active').textContent,/包含历史消息/);
  $('assistant-message-show_history').checked=false;const failed=run.loadMessages();pending.shift().reject(new Error('offline'));await failed;
  assert.match($('assistant-message-active').textContent,/包含历史消息/);
  assert.match($('assistant-message-error').textContent,/仍显示上次结果/);
  await run.loadMessages(true);assert.equal(pending.length,0);assert.equal(run.messages.cursor,null);
});
test('detail back preserves pages, cursor, scroll, title and focus without requesting homepage',async()=>{
  const {$,pending,run}=await fixture();const first=run.loadMessages();pending.shift().resolve({items:[sample()],next_cursor:'p2'});await first;
  const more=run.loadMessages(true);const page=pending.shift();assert.match(page.path,/cursor=p2/);page.resolve({items:[sample(),sample('n')],next_cursor:'p3'});await more;
  assert.equal($('assistant-message-list').children.length,2);
  const row=$('assistant-message-list').children[0],trigger=row.querySelector('button');
  $('assistant-message-scroll').scrollTop=180;
  const detail=run.openMessage('m',trigger);pending.shift().resolve({message:sample()});
  await new Promise(resolve=>setImmediate(resolve));const read=pending.shift();assert.equal(read.path,'/messages/read');read.resolve({});await detail;
  assert.match(row.textContent,/一项正文增补/);assert.match(row.textContent,/视频正文修改建议/);
  run.backToMessages();assert.equal($('assistant-message-scroll').scrollTop,180);assert.equal(run.messages.cursor,'p3');assert.equal(pending.length,0);assert(run.messages.trigger.focused.preventScroll);
});
test('late detail after back cannot overwrite next message or issue a read acknowledgement',async()=>{
  const {$,pending,run}=await fixture();const old=run.openMessage('old',new Element());const oldRequest=pending.shift();run.backToMessages();
  const next=run.openMessage('next',new Element());const nextRequest=pending.shift();oldRequest.resolve({message:sample('old')});await old;
  assert.equal(pending.length,0);assert.equal($('assistant-message-detail').textContent,'正在读取消息…');
  nextRequest.reject(new Error('offline'));await next;assert.match($('assistant-message-detail').textContent,/读取失败/);assert.equal($('assistant-message-list-view').hidden,true);run.backToMessages();assert.equal($('assistant-message-list-view').hidden,false);
});
test('old failure for same reopened message cannot replace newer detail',async()=>{
  const {$,pending,run}=await fixture();const old=run.openMessage('m',new Element());const oldRequest=pending.shift();run.backToMessages();
  const next=run.openMessage('m',new Element());pending.shift().resolve({message:sample()});await new Promise(resolve=>setImmediate(resolve));pending.shift().resolve({});await next;
  oldRequest.reject(new Error('older failed'));await old;assert.match($('assistant-message-detail').textContent,/视频正文修改建议/);assert(!/older failed/.test($('assistant-message-detail').textContent));
});

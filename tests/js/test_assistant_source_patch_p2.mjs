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

test('source review submits displayed versions and retains preview after conflict without regeneration',async()=>{
  const source=await readFile('src/shiliu/static/assistant.js','utf8');
  const code=source.slice(source.indexOf('  const messages ='),source.indexOf('  function showFatal('));
  const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  const calls=[],toasts=[];
  const message={id:'m',business_state:'pending',source_times:[],processing_times:[],created_at:'created',links:[],actions:[{kind:'proposal',id:'p',space_id:1,expected_content_version:3,expected_target_version:7},{kind:'proposal_refresh',id:'p',space_id:1}],detail:{kind:'source_patch',content_version:3,target_version:7,operation:'add_block',before:{blocks:[]},after:{blocks:[{heading:'已审内容',markdown:'原候选正文'}]}}};
  const context={Map,Date,document:{createElement:tag=>new Element(tag)},$,state:{},formatDate:x=>x,operationKey:()=> 'click-op',toast:t=>toasts.push(t),api:async(path,options)=>{
    calls.push({path,payload:options?.body?JSON.parse(options.body):null});
    if(path==='/messages/m')return {message};
    if(path==='/messages/unread-count')return {unread_count:0};
    if(path.endsWith('/decide'))throw new Error('wiki_proposal_review_version_conflict');
    return {};
  }};
  vm.createContext(context);vm.runInContext(code+'\nmessages.selected="m";this.run={showMessage,messages};',context);
  const article=new Element(),heading=new Element('button'),box=new Element();article.append(heading,box);
  await context.run.showMessage('m',box);
  const buttons=$('assistant-message-actions').querySelectorAll('button');
  const confirm=buttons.find(b=>b.textContent==='确认增补');
  assert(confirm);assert(buttons.some(b=>b.textContent.includes('正常模型额度')));
  await confirm.onclick();
  const decision=calls.find(c=>c.path.endsWith('/decide'));
  assert.equal(decision.payload.expected_content_version,3);
  assert.equal(decision.payload.expected_target_version,7);
  assert.equal(calls.filter(c=>c.path.endsWith('/decide')).length,1);
  assert.equal(calls.filter(c=>c.path.includes('request-refresh')).length,0);
  assert(box.children.some(c=>c.textContent.includes('原候选正文')));
  assert(box.textContent.includes('version_conflict'));
  assert(box.querySelectorAll('button').some(b=>b.textContent==='重新读取'));
  assert(buttons.every(b=>b.disabled));
});

test('successful decision updates list and return focus even when read acknowledgement fails',async()=>{
  const source=await readFile('src/shiliu/static/assistant.js','utf8');
  const code=source.slice(source.indexOf('  const messages ='),source.indexOf('  function showFatal('));
  const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  let applied=false;
  const initial={id:'m',object_label:'原标题',change_summary:'原摘要',business_state:'pending',read_at:null,links:[],actions:[{kind:'proposal',id:'p',expected_content_version:3,expected_target_version:7}],detail:{kind:'source_patch',operation:'add_block',content_version:3,target_version:7,after:{blocks:[{heading:'块',markdown:'审核正文'}]}}};
  const context={Map,Date,document:{createElement:tag=>new Element(tag)},$,state:{},operationKey:()=> 'click-op',toast:()=>{},api:async(path)=>{
    if(path==='/messages/m')return {message:applied?{...initial,business_state:'applied',actions:[]}:initial};
    if(path.endsWith('/decide')){applied=true;return {};}
    if(path==='/messages/read')throw new Error('read_offline');
    return {unread_count:0};
  }};
  vm.createContext(context);vm.runInContext(code+'\nmessages.selected="m";this.run={showMessage,messages,backToMessages};',context);
  const {run}=context;const article=new Element();run.messages.rows.set('m',{item:initial,article});
  await run.showMessage('m',$('assistant-message-detail'));
  await $('assistant-message-actions').querySelectorAll('button').find(b=>b.textContent==='确认增补').onclick();
  assert.equal(run.messages.rows.get('m').item.business_state,'applied');
  assert.match(article.textContent,/原标题/);assert.match(article.textContent,/原摘要/);assert.match(article.textContent,/已更新/);
  assert.equal(run.messages.trigger,article.querySelector('button'));
  run.backToMessages();assert(run.messages.trigger.focused.preventScroll);
  assert.match($('assistant-message-detail').textContent,/已读未保存/);
});

test('decision success followed by GET failure offers GET-only recovery and never resends decision',async()=>{
  const source=await readFile('src/shiliu/static/assistant.js','utf8');
  const code=source.slice(source.indexOf('  const messages ='),source.indexOf('  function showFatal('));
  const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  let decisions=0,fail=false;
  const message={id:'m',object_label:'原审核标题',business_state:'pending',links:[],actions:[{kind:'proposal',id:'p',expected_content_version:3,expected_target_version:7}],detail:{kind:'source_patch',operation:'add_block',content_version:3,target_version:7,after:{blocks:[{heading:'块',markdown:'原审核正文'}]}}};
  const context={Map,Date,document:{createElement:tag=>new Element(tag)},$,state:{},operationKey:()=> 'click-op',toast:()=>{},api:async(path)=>{
    if(path==='/messages/m'){if(fail)throw new Error('refresh_offline');return {message:decisions?{...message,business_state:'applied',actions:[]}:message};}
    if(path.endsWith('/decide')){decisions++;fail=true;return {};}
    return {unread_count:0};
  }};
  vm.createContext(context);vm.runInContext(code+'\nmessages.selected="m";this.run={showMessage};',context);
  const box=$('assistant-message-detail');await context.run.showMessage('m',box);
  await $('assistant-message-actions').querySelectorAll('button')[0].onclick();
  assert.match(box.textContent,/refresh_offline/);assert.match(box.textContent,/原审核正文/);
  assert($('assistant-message-actions').querySelectorAll('button').every(b=>b.disabled));
  fail=false;await box.querySelectorAll('button').find(b=>b.textContent==='重新读取').onclick();
  assert.equal(decisions,1);assert.match(box.textContent,/已更新/);assert($('assistant-message-actions').hidden);
});

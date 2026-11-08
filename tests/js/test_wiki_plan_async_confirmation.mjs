import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

test('historical plan confirmation displays acceptance, not a saved-page success', async () => {
  const source = await readFile('src/shiliu/static/assistant.js','utf8');
  const pivot = source.indexOf('const {plan:updated, job, save_feedback}');
  const start = source.lastIndexOf('button.onclick = async () => {',pivot);
  const end = source.indexOf('}; card.append(button);',pivot)+2;
  assert.ok(pivot > 0 && start > 0 && end > pivot);
  const notices=[],button={},seen=[];
  const context={button,plan:{id:'original',version:1},spaceId:1,accept:true,query:'',
    state:{threadId:'thread'},current:()=>true,operationKey:()=> 'one',
    api: async path=> {seen.push(path);return {job:{id:'job',thread_id:'thread',status:'queued'}};},
    toast:message=>notices.push(message),refreshWikiSaves:async()=>seen.push('refresh-jobs'),
    showSaveFeedback:()=>{throw Error('accepted is not completed');},
    loadKnowledge:async()=>{throw Error('do not erase acceptance on stale plan refresh');}};
  vm.createContext(context);vm.runInContext(source.slice(start,end),context);
  await button.onclick();
  assert.equal(button.disabled,true);
  assert.match(button.textContent,/已受理/);
  assert.match(notices[0],/尚未完成/);
  assert.ok(seen.includes('refresh-jobs'));
});

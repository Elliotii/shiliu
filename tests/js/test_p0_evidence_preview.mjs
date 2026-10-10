import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

class Node {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.classList = {add() {}, remove() {}};
  }

  get childNodes() { return this.children; }
  append(...nodes) { nodes.forEach(node => this.insertBefore(node, null)); }
  insertBefore(node, next) {
    node.remove();
    const index = next ? this.children.indexOf(next) : this.children.length;
    this.children.splice(index, 0, node);
    node.parent = this;
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(n => n !== this);
    this.parent = null;
  }
  replaceChildren(...nodes) { this.children.forEach(n => { n.parent = null; }); this.children = []; this.append(...nodes); }
  addEventListener() {}
  setAttribute(name, value) { this[name] = String(value); }
  getAttribute(name) { return this[name] || null; }
  querySelector() { return new Node(); }
  closest() { return null; }
  focus() {}
  scrollIntoView() {}
}

const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, new Node());
  return nodes.get(selector);
};

const form = node('[data-ask-form]');
form.elements = {
  q: new Node(),
  mode: {value: 'fast'},
  folder_id: new Node(),
  reading_state: new Node(),
  marked: new Node(),
  uploader_contains: new Node(),
  favorite_time_from: new Node(),
  favorite_time_to: new Node(),
  archived: new Node(),
  ignored: new Node(),
};
form.querySelector = () => new Node();

const root = new Node();
root.querySelector = selector => selector === '[data-ask-form]' ? form : node(selector);
root.querySelectorAll = () => [];

globalThis.location = {pathname: '/ask', search: ''};
globalThis.history = {pushState() {}, replaceState() {}};
globalThis.document = {
  querySelector: selector => selector === '[data-ask-page]' ? root : null,
};
globalThis.window = {
  addEventListener() {},
  setTimeout,
  clearTimeout,
  ShiliuAskKeyboard: {shouldSubmitOnEnter: () => false},
  ShiliuEvidenceUI: {
    element: (tag, className, text) => {
      const result = new Node();
      result.tagName = tag;
      result.className = className;
      result.textContent = text === undefined ? '' : String(text);
      return result;
    },
    formatTime: value => {
      const seconds = Math.floor(Number(value));
      return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    },
    renderEvidenceCard: options => {
      const result = new Node();
      result.options = options;
      return result;
    },
    sourceLabels: {human: '人工字幕', unknown: '字幕'},
  },
};

const source = await readFile(
  new URL('../../src/shiliu/static/ask.js', import.meta.url),
  'utf8',
);
vm.runInThisContext(source, {filename: 'ask.js'});

const api = window.__shiliuAsk;
const preview = node('[data-evidence-preview]');
const previewList = node('[data-preview-evidence-list]');
const previewTitle = node('[data-preview-title]');
const item = {
  citation_id: 'citation-1',
  video_id: 1,
  title: 'MCP 视频',
  source_type: 'human',
  start_time: 75,
  end_time: 90,
  quote_text: 'MCP 通过协议连接模型与外部工具。',
  jump_url: 'https://www.bilibili.com/video/BV1?t=75',
};

const result = (executionOutcome, overrides = {}) => ({
  run_id: 'ask-run-1',
  mode: 'fast',
  status: executionOutcome === 'answer_generated' ? 'complete' : 'insufficient',
  execution_outcome: executionOutcome,
  termination_reason: executionOutcome === 'generation_failed' ? 'provider_error' : 'answer_ready',
  answer_blocks: executionOutcome === 'answer_generated'
    ? [{text: '有证据支持的回答', citation_ids: []}]
    : [],
  citations: [],
  limitations: [],
  trace_summary: {},
  ...overrides,
});

test('Loading shows deduplicated jumpable Preview; Final hides it', () => {
  api.resetPreview();
  api.showState('loading');
  api.showLifecycle({
    event_type: 'evidence_preview',
    sequence: 4,
    payload: {items: [item, item, {...item, citation_id: 'citation-2'}]},
  });

  assert.equal(preview.hidden, false);
  assert.equal(previewList.children.length, 2);
  assert.equal(previewList.children[0].options.jumpLabel, '从 1:15 播放');
  assert.equal(previewList.children[0].options.jumpUrl, item.jump_url);
  assert.equal(node('[data-preview-count]').textContent, '2 条片段');
  assert.equal(
    previewTitle.textContent,
    '已找到一些可能相关的视频片段，正在生成带引用的回答。',
  );

  api.renderResult(result('answer_generated', {
    citations: [item],
    candidate_disclosure: {candidates: []},
  }));
  assert.equal(node('[data-result-state]').hidden, false);
  assert.equal(preview.hidden, true);
  assert.equal(node('[data-evidence-section]').hidden, false);
  assert.equal(node('[data-citation-groups]').children.length, 1);
  assert.equal(node('[data-candidate-disclosure]').hidden, false);
  assert.equal(node('[data-candidate-disclosure]').open, false);
});

test('generation failure retains preview while final insufficient clears it', () => {
  api.resetPreview();
  api.showLifecycle({event_type: 'evidence_preview', payload: {items: [item]}});
  api.renderResult(result('generation_failed'));

  assert.equal(preview.hidden, false);
  assert.equal(previewList.children.length, 1);
  assert.equal(previewTitle.textContent, '已找到相关内容，但本次回答生成失败。');
  assert.equal(
    node('[data-preview-copy]').textContent,
    '你仍然可以查看下面的视频片段。',
  );

  api.showLifecycle({event_type: 'evidence_preview', payload: {items: [item]}});
  api.renderResult(result('evidence_insufficient'));
  assert.equal(preview.hidden, true);
  assert.equal(previewList.children.length, 0);
  assert.equal(node('[data-termination-copy]').textContent, '未找到足够证据');
});

test('successful answer overrides residual provider failure copy', () => {
  api.renderResult(result('answer_generated', {
    status: 'partial',
    termination_reason: 'provider_error',
    limitations: ['只回答了部分问题'],
  }));
  assert.equal(
    node('[data-termination-copy]').textContent,
    '已找到可用字幕证据并完成本次回答',
  );

  api.renderResult(result('generation_failed'));
  assert.equal(node('[data-termination-copy]').textContent, '回答服务暂时不可用');
});


test('Deep valid evidence count is independent of citations; missing is not zero', () => {
  api.renderResult(result('answer_generated', {
    mode: 'deep', citations: [item], trace_summary: {valid_evidence_count: 6},
  }));
  const metric = () => node('[data-trace-metrics]').children.find(
    entry => entry.children[0].textContent === '有效字幕证据',
  ).children[1].textContent;
  assert.equal(metric(), '6');
  api.renderResult(result('answer_generated'));
  assert.equal(metric(), '未记录');
});

test('capacity note stays quiet while real limitations retain warning panel', () => {
  const budget = '上下文预算已截断部分候选证据';
  api.renderResult(result('answer_generated', {limitations: [budget]}));
  assert.equal(node('[data-context-scope-note]').hidden, false);
  assert.equal(node('[data-limitations-panel]').hidden, true);
  api.renderResult(result('generation_failed', {limitations: [budget, '回答服务不可用']}));
  assert.equal(node('[data-limitations-panel]').hidden, false);
  assert.deepEqual(node('[data-limitations-list]').children.map(x => x.textContent), ['回答服务不可用']);
  api.renderResult(result('evidence_insufficient', {limitations: ['没有足够证据']}));
  assert.equal(node('[data-context-scope-note]').hidden, true);
  assert.equal(node('[data-limitations-panel]').hidden, false);
});

test('optional framing surrounds cited blocks as plain text and never replaces insufficient', () => {
  const intro = '<script>intro</script>';
  api.renderResult(result('answer_generated', {
    intro, outro: '口味因人而异。', citations: [item],
    answer_blocks: [{text: '有引用的正文', citation_ids: [item.citation_id]}],
  }));
  const body = node('[data-answer-blocks]');
  assert.equal(body.children.length, 3);
  assert.equal(body.children[0].textContent, intro);
  assert.equal(body.children[1].children[0].textContent, '有引用的正文');
  assert.equal(body.children[1].children[0].children[0].children[0].textContent, '[1]');
  assert.equal(body.children[2].textContent, '口味因人而异。');
  api.renderResult(result('evidence_insufficient', {intro, outro: '不应展示'}));
  assert.equal(body.children.length, 1);
  assert.notEqual(body.children[0].textContent, intro);
  api.renderResult(result('answer_generated'));
  assert.equal(body.children.length, 1);
});

const visibleText = node => node.textContent + node.children.map(visibleText).join('');

test('display emphasis preserves raw answer, citation mapping and text-only content in Fast and Deep', () => {
  for (const mode of ['fast', 'deep']) {
    const text = '**经典小吃**：生煎。也有**面馆**。<img src=x onerror=alert(1)> [伪引用](javascript:alert(1))';
    const data = result('answer_generated', {
      mode, intro: '**概述**：按分类介绍。', outro: '请**核实营业情况**。',
      answer_blocks: [{text, citation_ids: [item.citation_id, 'unknown']}], citations: [item],
    });
    const before = JSON.stringify(data);
    api.renderResult(data);
    const body = node('[data-answer-blocks]');
    assert.equal(body.children[0].className, 'answer-intro');
    assert.equal(body.children[2].className, 'answer-outro');
    assert.equal(visibleText(body.children[0]), '概述：按分类介绍。');
    assert.equal(visibleText(body.children[2]), '请核实营业情况。');
    const paragraph = body.children[1].children[0];
    assert.deepEqual(paragraph.children.filter(n => n.tagName === 'strong').map(n => n.textContent), ['经典小吃', '面馆']);
    assert.equal(visibleText(paragraph), text.replaceAll('**', '') + '[1]');
    const markers = paragraph.children.at(-1);
    assert.equal(markers.children.length, 1);
    assert.equal(markers.children[0].dataset.citationId, item.citation_id);
    assert.equal(markers.children[0]['aria-label'], '定位到回答依据 1');
    assert.equal(paragraph.children.some(n => ['img', 'script', 'a'].includes(n.tagName)), false);
    assert.equal(JSON.stringify(data), before);
  }
});

test('unsupported, escaped and incomplete formatting stays literal', () => {
  for (const text of [
    '普通正文', '**没有结尾', '没有开头**', '***三重星号***', '**结尾三颗***',
    '** 两边空格 **', '**跨\n行**', String.raw`\**转义**`, '`**代码内容**`',
    '# 标题\n- 列表\n[链接](https://example.com) ![图](x) *斜体*',
  ]) {
    api.renderResult(result('answer_generated', {answer_blocks: [{text, citation_ids: []}]}));
    const paragraph = node('[data-answer-blocks]').children[0].children[0];
    assert.equal(visibleText(paragraph), text);
    assert.equal(paragraph.children.some(n => n.tagName === 'strong'), false);
  }
  const text = String.raw`\**转义**，**有效粗体**，末尾**未闭合`;
  api.renderResult(result('answer_generated', {answer_blocks: [{text, citation_ids: []}]}));
  const paragraph = node('[data-answer-blocks]').children[0].children[0];
  assert.equal(visibleText(paragraph), String.raw`\**转义**，有效粗体，末尾**未闭合`);
});

const stream = (sequence, event_type, payload, source_id = 'stream-run') => ({sequence, event_type, payload, source_id});

test('real block events append before terminal result, deduplicate and reconcile locally', () => {
  api.showLifecycle(stream(1, 'answer_generation_started', {started_at_ms: Date.now()}));
  const first = {text: '**先到的正文**', citation_ids: [item.citation_id]};
  api.showLifecycle(stream(2, 'answer_part', {generation: 0, index: 0, block: first,
    intro: '开头', outro: null, citations: [item]}));
  const body = node('[data-answer-blocks]');
  const firstNode = body.children[1];
  const firstCard = node('[data-citation-groups]').children[0].children[1];
  assert.equal(node('[data-result-state]').hidden, false);
  assert.equal(node('[data-status-badge]').hidden, true);
  assert.equal(body.children.length, 2);
  const second = {text: '后到的正文', citation_ids: [item.citation_id]};
  const secondEvent = stream(3, 'answer_part', {generation: 0, index: 2, block: second,
    intro: '开头', outro: null, citations: [item]});
  api.showLifecycle(secondEvent);
  api.showLifecycle(secondEvent);
  assert.equal(body.children.length, 3);
  assert.equal(body.children[1], firstNode);
  assert.equal(node('[data-citation-groups]').children[0].children[1], firstCard);
  api.showLifecycle(stream(4, 'answer_generation_finished', {generation: 0, generation_ms: 50, completed_at_ms: Date.now()}));
  assert.equal(window.__shiliuAnswerStream.generationMs, 50);
  const fixed = {text: '中间修复的正文', citation_ids: [item.citation_id]};
  api.renderResult(result('answer_generated', {run_id:'stream-run', intro: '开头', outro: '结尾',
    citations:[item], answer_blocks:[first, fixed, second], limitations:['真实缺口'],status:'partial'}));
  assert.equal(body.children.length, 5);
  assert.equal(body.children[1], firstNode);
  assert.equal(node('[data-citation-groups]').children[0].children[1], firstCard);
  assert.equal(node('[data-status-badge]').hidden, false);
  assert.equal(node('[data-limitations-panel]').hidden, false);
});

test('retry generations and final insufficient retract provisional answers', () => {
  api.showLifecycle(stream(1, 'answer_generation_started', {started_at_ms:Date.now()},'retry-run'));
  const part = {generation:0,index:0,block:{text:'临时正文',citation_ids:[item.citation_id]},citations:[item]};
  api.showLifecycle(stream(2,'answer_part',part,'retry-run'));
  api.showLifecycle(stream(3,'answer_stream_reset',{generation:1},'retry-run'));
  assert.equal(node('[data-answer-blocks]').children.length,0);
  assert.equal(node('[data-loading-state]').hidden,false);
  api.showLifecycle(stream(4,'answer_part',part,'retry-run'));
  assert.equal(node('[data-answer-blocks]').children.length,0);
  api.showLifecycle(stream(5,'answer_part',{...part,generation:1},'other-run'));
  assert.equal(node('[data-answer-blocks]').children.length,0);
  api.showLifecycle(stream(6,'answer_part',{...part,generation:1},'retry-run'));
  assert.equal(node('[data-answer-blocks]').children.length,1);
  api.renderResult(result('generation_failed',{run_id:'retry-run'}));
  assert.equal(node('[data-answer-blocks]').children.length,1);
  assert.match(visibleText(node('[data-answer-blocks]')), /未能生成/);
  assert.equal(node('[data-evidence-section]').hidden,true);
});

test('terminal authority ignores late parts and connection errors clear temporary content', () => {
  api.showLifecycle(stream(1,'answer_generation_started',{started_at_ms:Date.now()},'late-run'));
  const payload={generation:0,index:0,block:{text:'提前正文',citation_ids:[item.citation_id]},citations:[item]};
  api.showLifecycle(stream(2,'answer_part',payload,'late-run'));
  api.renderResult(result('answer_generated',{run_id:'late-run',answer_blocks:[{text:'最终正文',citation_ids:[item.citation_id]}],citations:[item]}));
  const body=node('[data-answer-blocks]');const official=body.children[0];
  api.showLifecycle(stream(3,'answer_part',{...payload,index:1},'late-run'));
  assert.equal(body.children.length,1);
  assert.equal(body.children[0],official);
  assert.equal(visibleText(official),'最终正文[1]');
  api.showLifecycle(stream(1,'answer_generation_started',{started_at_ms:Date.now()},'broken-run'));
  api.showLifecycle(stream(2,'answer_part',payload,'broken-run'));
  api.showError(500,{});
  assert.equal(body.children.length,0);
  assert.equal(node('[data-error-state]').hidden,false);
  assert.equal(window.__shiliuAnswerStream,null);
});


test('a retracted block before the next frame is not recorded as visible', () => {
  const frames = [];
  window.requestAnimationFrame = callback => frames.push(callback);
  api.showLifecycle(stream(1, 'answer_generation_started', {started_at_ms:Date.now()}, 'paint-run'));
  const part = {generation:0,index:0,block:{text:'待显示正文',citation_ids:[item.citation_id]},citations:[item]};
  api.showLifecycle(stream(2, 'answer_part', part, 'paint-run'));
  api.showLifecycle(stream(3, 'answer_stream_reset', {generation:1}, 'paint-run'));
  frames.shift()();
  assert.equal(window.__shiliuAnswerStream.firstVisibleAtMs, undefined);
  api.showLifecycle(stream(4, 'answer_part', {...part,generation:1}, 'paint-run'));
  frames.shift()();
  assert.equal(typeof window.__shiliuAnswerStream.firstVisibleAtMs, 'number');
  delete window.requestAnimationFrame;
});


test('actual Jev dispatch changes lifecycle text; batch audit events leave it alone', () => {
  const lifecycle=node('[data-lifecycle-status]');
  api.showLifecycle({event_type:'deep_research',sequence:1,payload:{phase:'reduce_started'}});
  assert.equal(lifecycle.textContent,'正在筛选并整理检索证据');
  api.showLifecycle({event_type:'deep_research',sequence:2,payload:{phase:'jev_started'}});
  assert.equal(lifecycle.textContent,'正在使用 Jev 筛选并整理检索证据');
  api.showLifecycle({event_type:'deep_research',sequence:3,payload:{phase:'controller_started'}});
  assert.equal(lifecycle.textContent,'正在规划后续研究');
  api.showLifecycle({event_type:'b0_batch',payload:{accepted:true}});
  assert.equal(lifecycle.textContent,'正在规划后续研究');
});

test('source navigation survives progressive display adapter', () => {
  api.renderResult(result('source_lookup_complete',{status:'complete',mode:'deep',
    source_matches:[{video_id:7,title:'Located source'}]}));
  const card=node('[data-candidate-list]').children[0];
  assert.equal(card.children.at(-1).href,'/videos/7');
  assert.equal(node('[data-status-badge]').textContent,'已找到相关视频');
});

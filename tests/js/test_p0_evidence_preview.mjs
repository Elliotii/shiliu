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
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
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
    element: (_tag, _className, text) => {
      const result = new Node();
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

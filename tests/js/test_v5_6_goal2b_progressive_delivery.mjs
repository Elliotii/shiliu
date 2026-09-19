import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const ask = await readFile(new URL('../../src/shiliu/static/ask.js', import.meta.url), 'utf8');
const research = await readFile(new URL('../../src/shiliu/static/research.js', import.meta.url), 'utf8');
const askTemplate = await readFile(new URL('../../src/shiliu/templates/ask.html', import.meta.url), 'utf8');

test('Ask projects durable Fast and Deep events without timer-derived stages', () => {
  assert.match(ask, /fetch\('\/api\/ask\/stream'/);
  assert.match(ask, /fetch\('\/api\/ask\/runs'/);
  assert.match(ask, /after_sequence=\$\{cursor\}/);
  assert.match(ask, /showLifecycle\(event\)/);
  assert.doesNotMatch(ask, /elapsedTimer|data-elapsed-time|fake percentage/i);
  assert.match(askTemplate, /data-lifecycle-status/);
  assert.doesNotMatch(askTemplate, /data-elapsed-time/);
});

test('Fast, Deep, and Research expose explicit non-authoritative Draft save', () => {
  assert.match(ask, /source_kind: 'ask_run'/);
  assert.match(ask, /Draft 已保存/);
  assert.match(research, /source_kind: 'research_task'/);
  assert.match(research, /data-research-draft-status/);
  assert.match(askTemplate, /Draft 不是 Fact、引用权威或已发布长期知识/);
});

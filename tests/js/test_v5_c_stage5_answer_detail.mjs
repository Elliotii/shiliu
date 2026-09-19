import assert from 'node:assert/strict';
import test from 'node:test';

await import('../../src/shiliu/static/research-personalization.js');

const ui = globalThis.ShiliuResearchPersonalization;

class Container {
  constructor(name, children = []) {
    this.name = name;
    this.children = children;
    this.hidden = false;
  }

  get firstChild() { return this.children[0] || null; }

  append(node) {
    for (const owner of owners) owner.children = owner.children.filter(item => item !== node);
    this.children.push(node);
  }
}

const owners = [];

const fixture = () => {
  owners.splice(0);
  const blocks = [
    {text: 'first', citations: ['c1']},
    {text: 'second', citations: ['c2']},
    {text: 'third', citations: ['c3', 'c4']},
  ];
  const answer = new Container('answer', [...blocks]);
  const compact = new Container('compact');
  const details = {hidden: true};
  owners.push(answer, compact);
  return {blocks, answer, compact, details};
};

test('compact moves only secondary existing block nodes and standard restores exact order', () => {
  const value = fixture();
  const evidence = [{id: 'e1'}, {id: 'e2'}];
  const compact = ui.applyAnswerDetail(
    value.answer,
    value.details,
    value.compact,
    {enabled: true, detail_applied: true, detail_preference: {value: 'compact'}},
  );
  assert.deepEqual(compact, {detailLevel: 'compact', compactedCount: 2});
  assert.deepEqual(value.answer.children, [value.blocks[0]]);
  assert.deepEqual(value.compact.children, [value.blocks[1], value.blocks[2]]);
  assert.equal(value.details.hidden, false);
  assert.deepEqual(value.blocks.map(block => block.text), ['first', 'second', 'third']);
  assert.deepEqual(value.blocks.map(block => block.citations), [['c1'], ['c2'], ['c3', 'c4']]);
  assert.deepEqual(evidence, [{id: 'e1'}, {id: 'e2'}]);

  const standard = ui.applyAnswerDetail(
    value.answer,
    value.details,
    value.compact,
    {enabled: false, detail_applied: true, detail_preference: {value: 'compact'}},
  );
  assert.deepEqual(standard, {detailLevel: 'standard', compactedCount: 2});
  assert.deepEqual(value.answer.children, value.blocks);
  assert.deepEqual(value.compact.children, []);
  assert.equal(value.details.hidden, true);
});

test('candidate, unknown, and zero-secondary contexts preserve standard baseline', () => {
  for (const context of [
    {enabled: true, detail_applied: false, detail_preference: {value: 'compact'}},
    {enabled: true, detail_applied: true, detail_preference: {value: 'unknown'}},
  ]) {
    const value = fixture();
    const outcome = ui.applyAnswerDetail(value.answer, value.details, value.compact, context);
    assert.equal(outcome.detailLevel, 'standard');
    assert.deepEqual(value.answer.children, value.blocks);
    assert.equal(value.details.hidden, true);
  }
  owners.splice(0);
  const only = {text: 'only', citations: ['c1']};
  const answer = new Container('answer', [only]);
  const compact = new Container('compact');
  const details = {hidden: true};
  owners.push(answer, compact);
  const outcome = ui.applyAnswerDetail(
    answer,
    details,
    compact,
    {enabled: true, detail_applied: true, detail_preference: {value: 'compact'}},
  );
  assert.deepEqual(outcome, {detailLevel: 'compact', compactedCount: 0});
  assert.deepEqual(answer.children, [only]);
  assert.equal(details.hidden, true);
});

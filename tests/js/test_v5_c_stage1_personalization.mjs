import assert from 'node:assert/strict';
import test from 'node:test';

await import('../../src/shiliu/static/research-personalization.js');

const ui = globalThis.ShiliuResearchPersonalization;

const fixture = () => {
  const answerBlocks = {name: 'answer'};
  const limitations = {name: 'limitations'};
  const section = {
    children: [answerBlocks, limitations],
    insertBefore(node, target) {
      this.children = this.children.filter(value => value !== node);
      this.children.splice(this.children.indexOf(target), 0, node);
    },
  };
  answerBlocks.after = node => {
    section.children = section.children.filter(value => value !== node);
    section.children.splice(section.children.indexOf(answerBlocks) + 1, 0, node);
  };
  return {section, answerBlocks, limitations};
};

test('confirmed treatment moves only the limitations container before the answer', () => {
  const value = fixture();
  const position = ui.applyAnswerPresentation(
    value.section,
    value.answerBlocks,
    value.limitations,
    {enabled: true, applied: true, preference: {value: 'before_answer'}},
  );
  assert.equal(position, 'before_answer');
  assert.deepEqual(value.section.children, [value.limitations, value.answerBlocks]);
});

test('no profile, disabled, and unrelated values preserve the after-answer baseline', () => {
  for (const context of [
    {enabled: true, applied: false, preference: null},
    {enabled: false, applied: false, preference: {value: 'before_answer'}},
    {enabled: true, applied: true, preference: {value: 'unrelated'}},
  ]) {
    const value = fixture();
    const position = ui.applyAnswerPresentation(
      value.section, value.answerBlocks, value.limitations, context,
    );
    assert.equal(position, 'after_answer');
    assert.deepEqual(value.section.children, [value.answerBlocks, value.limitations]);
  }
});

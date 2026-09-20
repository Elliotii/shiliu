import assert from 'node:assert/strict';
import test from 'node:test';

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.textContent = '';
  }

  append(...nodes) { this.children.push(...nodes); }
  addEventListener(name, handler) { this[`on${name}`] = handler; }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  click() { this.onclick?.({type: 'click'}); }
}

globalThis.window = globalThis;
globalThis.document = {createElement: tagName => new FakeElement(tagName)};
await import('../../src/shiliu/static/evidence-ui.js');

const ui = globalThis.ShiliuEvidenceUI;
const descendants = node => [node, ...node.children.flatMap(descendants)];
const byClass = (node, className) => descendants(node).find(value =>
  String(value.className || '').split(' ').includes(className)
);

test('short evidence remains complete and has no expand control', () => {
  const quote = '短依据原文';
  const card = ui.renderEvidenceCard({id: 'short', quote});
  assert.equal(byClass(card, 'evidence-ui-quote').textContent, quote);
  assert.equal(byClass(card, 'evidence-ui-expand'), undefined);
});

test('long evidence expands verbatim, collapses to preview, and cards stay independent', () => {
  const firstText = '甲'.repeat(ui.EVIDENCE_PREVIEW_LENGTH + 30);
  const secondText = '乙'.repeat(ui.EVIDENCE_PREVIEW_LENGTH + 40);
  const first = ui.renderEvidenceCard({id: 'first', quote: firstText});
  const second = ui.renderEvidenceCard({id: 'second', quote: secondText});
  const firstQuote = byClass(first, 'evidence-ui-quote');
  const firstButton = byClass(first, 'evidence-ui-expand');
  const secondQuote = byClass(second, 'evidence-ui-quote');
  const secondButton = byClass(second, 'evidence-ui-expand');

  assert.equal(firstButton.tagName, 'BUTTON');
  assert.equal(firstButton.type, 'button');
  assert.equal(firstButton.getAttribute('aria-expanded'), 'false');
  assert.equal(firstQuote.textContent, `${'甲'.repeat(ui.EVIDENCE_PREVIEW_LENGTH)}…`);
  firstButton.click();
  assert.equal(firstButton.getAttribute('aria-expanded'), 'true');
  assert.equal(firstQuote.textContent, firstText);
  assert.notEqual(secondQuote.textContent, secondText);
  assert.equal(secondButton.getAttribute('aria-expanded'), 'false');
  firstButton.click();
  assert.equal(firstButton.getAttribute('aria-expanded'), 'false');
  assert.equal(firstQuote.textContent, `${'甲'.repeat(ui.EVIDENCE_PREVIEW_LENGTH)}…`);
});

test('local absolute time formatting handles UTC, offsets, empty, and invalid values', () => {
  for (const value of ['2026-08-29T07:24:18.123456Z', '2026-08-29T15:24:18.123456+08:00']) {
    const formatted = ui.formatLocalDateTime(value);
    assert.match(formatted, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    assert.doesNotMatch(formatted, /T|Z|\.\d|[+-]\d{2}:\d{2}$/);
  }
  assert.equal(ui.formatLocalDateTime(''), '');
  assert.equal(ui.formatLocalDateTime('not-a-date'), 'not-a-date');
});

(function (root, factory) {
  const api = factory();
  if (root) root.ShiliuAskKeyboard = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
}(typeof window !== 'undefined' ? window : globalThis, () => ({
  shouldSubmitOnEnter: event => (
    event.key === 'Enter'
    && !event.shiftKey
    && !event.isComposing
    && event.keyCode !== 229
  ),
})));

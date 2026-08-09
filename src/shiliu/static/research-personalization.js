(() => {
  const DEFAULT_POSITION = 'after_answer';

  const presentationPosition = context => (
    context?.enabled === true
    && context?.applied === true
    && context?.preference?.value === 'before_answer'
      ? 'before_answer'
      : DEFAULT_POSITION
  );

  const applyAnswerPresentation = (section, answerBlocks, limitations, context) => {
    const position = presentationPosition(context);
    if (position === 'before_answer') section.insertBefore(limitations, answerBlocks);
    else answerBlocks.after(limitations);
    return position;
  };

  globalThis.ShiliuResearchPersonalization = {
    DEFAULT_POSITION,
    presentationPosition,
    applyAnswerPresentation,
  };
})();

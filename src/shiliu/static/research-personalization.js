(() => {
  const DEFAULT_POSITION = 'after_answer';
  const DEFAULT_DETAIL_LEVEL = 'standard';

  const presentationPosition = context => (
    context?.enabled === true
    && context?.applied === true
    && context?.preference?.value === 'before_answer'
      ? 'before_answer'
      : DEFAULT_POSITION
  );

  const detailLevel = context => (
    context?.enabled === true
    && context?.detail_applied === true
    && context?.detail_preference?.value === 'compact'
      ? 'compact'
      : DEFAULT_DETAIL_LEVEL
  );

  const applyAnswerDetail = (answerBlocks, compactDetails, compactBlocks, context) => {
    while (compactBlocks.firstChild) answerBlocks.append(compactBlocks.firstChild);
    const level = detailLevel(context);
    const secondary = Array.from(answerBlocks.children).slice(1);
    if (level === 'compact' && secondary.length) {
      secondary.forEach(block => compactBlocks.append(block));
      compactDetails.hidden = false;
    } else compactDetails.hidden = true;
    return {detailLevel: level, compactedCount: secondary.length};
  };

  const applyAnswerPresentation = (
    section, answerBlocks, limitations, context, answerTail = answerBlocks,
  ) => {
    const position = presentationPosition(context);
    if (position === 'before_answer') section.insertBefore(limitations, answerBlocks);
    else answerTail.after(limitations);
    return position;
  };

  globalThis.ShiliuResearchPersonalization = {
    DEFAULT_POSITION,
    DEFAULT_DETAIL_LEVEL,
    presentationPosition,
    detailLevel,
    applyAnswerDetail,
    applyAnswerPresentation,
  };
})();

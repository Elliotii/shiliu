(() => {
  const sourceLabels = {
    human: '人工字幕',
    ai: 'AI 字幕',
    asr: 'ASR 转录',
    unknown: '字幕',
  };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };

  const formatTime = value => {
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
      : `${minutes}:${String(rest).padStart(2, '0')}`;
  };

  const formatDuration = value => {
    const seconds = Math.max(0, Math.round(Number(value) || 0));
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    if (!minutes) return `${rest}秒`;
    return rest ? `${minutes}分${rest}秒` : `${minutes}分钟`;
  };

  const renderEvidenceCard = options => {
    const card = element(options.tagName || 'article', `evidence-ui-card ${options.className || ''}`.trim());
    if (options.id) card.id = options.id;
    if (options.evidenceId) card.dataset.evidenceId = options.evidenceId;
    if (options.videoId !== undefined) card.dataset.videoId = String(options.videoId);
    card.tabIndex = -1;

    const heading = element('div', 'evidence-ui-heading');
    const titleBlock = element('div', 'evidence-ui-title-block');
    if (options.eyebrow) titleBlock.append(element('p', 'evidence-ui-eyebrow', options.eyebrow));
    titleBlock.append(element('h3', 'evidence-ui-title', options.title || '字幕证据'));
    heading.append(titleBlock);
    const range = options.timeRange || `${formatTime(options.startTime)}–${formatTime(options.endTime)}`;
    heading.append(element('span', 'evidence-ui-range', range));
    card.append(heading);

    if (options.contextLabel || options.contextSummary) {
      const context = element('div', 'evidence-ui-context');
      if (options.contextLabel) context.append(element('strong', '', options.contextLabel));
      if (options.contextSummary) context.append(element('span', '', options.contextSummary));
      card.append(context);
    }

    card.append(element('blockquote', 'evidence-ui-quote', options.quote || '该时间段暂无可显示的字幕摘录。'));

    const footer = element('div', 'evidence-ui-footer');
    const tags = element('div', 'evidence-ui-tags');
    const sourceTypes = options.sourceTypes || (options.sourceType ? [options.sourceType] : []);
    sourceTypes.forEach(source => {
      tags.append(element('span', 'evidence-ui-tag', sourceLabels[source] || sourceLabels.unknown));
    });
    if (options.durationText) tags.append(element('span', 'evidence-ui-tag', options.durationText));
    footer.append(tags);
    if (options.jumpUrl) {
      const link = element('a', 'evidence-ui-jump', options.jumpLabel || `从 ${formatTime(options.startTime)} 播放`);
      link.href = options.jumpUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      if (options.jumpSource) link.dataset.jumpSource = options.jumpSource;
      footer.append(link);
    }
    card.append(footer);

    if (options.metadata?.length) {
      const details = element('details', 'evidence-ui-metadata');
      details.append(element('summary', '', options.metadataLabel || '证据身份与来源'));
      const values = element('dl', 'evidence-ui-metadata-grid');
      options.metadata.forEach(([term, value]) => {
        values.append(element('dt', '', term), element('dd', '', value || '—'));
      });
      details.append(values);
      card.append(details);
    }
    return card;
  };

  window.ShiliuEvidenceUI = {
    element,
    formatDuration,
    formatTime,
    renderEvidenceCard,
    sourceLabels,
  };
})();

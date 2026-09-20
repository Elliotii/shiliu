(() => {
  const EVIDENCE_PREVIEW_LENGTH = 240;
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

  const formatLocalDateTime = value => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const pad = part => String(part).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  const previewText = (value, limit = EVIDENCE_PREVIEW_LENGTH) => {
    const text = String(value || '');
    const characters = Array.from(text);
    if (characters.length <= limit) return {text, truncated: false};
    return {text: `${characters.slice(0, limit).join('').trimEnd()}…`, truncated: true};
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

    const quoteText = options.quote || '该时间段暂无可显示的字幕摘录。';
    const preview = previewText(quoteText);
    const quote = element('blockquote', 'evidence-ui-quote', preview.text);
    quote.id = `${options.id || `evidence-${String(options.evidenceId || 'quote')}`}-quote`;
    card.append(quote);

    let expandButton = null;
    if (preview.truncated) {
      expandButton = element('button', 'evidence-ui-expand', '展开原文');
      expandButton.type = 'button';
      expandButton.setAttribute('aria-expanded', 'false');
      expandButton.setAttribute('aria-controls', quote.id);
      expandButton.addEventListener('click', () => {
        const expanded = expandButton.getAttribute('aria-expanded') === 'true';
        quote.textContent = expanded ? preview.text : quoteText;
        expandButton.textContent = expanded ? '展开原文' : '收起原文';
        expandButton.setAttribute('aria-expanded', String(!expanded));
      });
    }

    const footer = element('div', 'evidence-ui-footer');
    const tags = element('div', 'evidence-ui-tags');
    const sourceTypes = options.sourceTypes || (options.sourceType ? [options.sourceType] : []);
    sourceTypes.forEach(source => {
      tags.append(element('span', 'evidence-ui-tag', sourceLabels[source] || sourceLabels.unknown));
    });
    if (options.sourceStatus) tags.append(element('span', 'evidence-ui-tag', options.sourceStatus));
    if (options.durationText) tags.append(element('span', 'evidence-ui-tag', options.durationText));
    footer.append(tags);
    const actions = element('div', 'evidence-ui-actions');
    if (expandButton) actions.append(expandButton);
    if (options.jumpUrl) {
      const link = element('a', 'evidence-ui-jump', options.jumpLabel || '打开原视频');
      link.href = options.jumpUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      if (options.jumpSource) link.dataset.jumpSource = options.jumpSource;
      actions.append(link);
    }
    footer.append(actions);
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
    EVIDENCE_PREVIEW_LENGTH,
    element,
    formatDuration,
    formatLocalDateTime,
    formatTime,
    previewText,
    renderEvidenceCard,
    sourceLabels,
  };
})();

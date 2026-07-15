const libraryRequest = async (url, options = {}) => {
  const response = await fetch(url, {
    method: options.method || 'GET',
    headers: options.body ? {'Content-Type': 'application/json'} : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  return data;
};

const cardsForVideo = id => [...document.querySelectorAll(`.video-card[data-video-id="${id}"]`)];
const showNoteError = (card, message) => {
  const node = card.querySelector('[data-note-error]');
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
};

document.addEventListener('click', async event => {
  const reading = event.target.closest('[data-reading-value]');
  if (reading) {
    const card = reading.closest('[data-video-id]');
    try {
      const data = await libraryRequest(`/api/videos/${card.dataset.videoId}/reading-state`, {method: 'PATCH', body: {reading_state: reading.dataset.readingValue}});
      cardsForVideo(card.dataset.videoId).forEach(item => {
        item.querySelector('[data-reading-state]')?.setAttribute('data-reading-state', data.video.reading_state);
        item.classList.toggle('is-read', data.video.reading_state === 'read');
      });
    } catch (error) { alert(error.message); }
    return;
  }

  const collapseSummary = event.target.closest('[data-collapse-summary]');
  if (collapseSummary) {
    const details = collapseSummary.closest('details');
    if (details) details.open = false;
    return;
  }

  const control = event.target.closest('[data-library-action]');
  if (control) {
    const card = control.closest('[data-video-id]');
    const id = card.dataset.videoId;
    const action = control.dataset.libraryAction;
    const enabled = action === 'mark' ? control.getAttribute('aria-pressed') !== 'true' : !card.classList.contains('is-archived');
    try {
      const data = await libraryRequest(`/api/videos/${id}/${action}`, {method: enabled ? 'POST' : 'DELETE'});
      if (action === 'mark') {
        cardsForVideo(id).forEach(item => {
          item.classList.toggle('is-marked', data.video.is_marked);
          item.querySelector('.mark-toggle')?.setAttribute('aria-pressed', String(data.video.is_marked));
          item.querySelector('.mark-toggle')?.setAttribute('aria-label', data.video.is_marked ? '取消 Mark' : 'Mark');
          const badge = item.querySelector('.mark-badge');
          if (badge) badge.hidden = !data.video.is_marked;
        });
        if (!data.video.is_marked && document.querySelector('[data-library-view]')?.dataset.libraryView === 'marked') cardsForVideo(id).forEach(item => item.remove());
      } else {
        cardsForVideo(id).forEach(item => item.remove());
      }
    } catch (error) { alert(error.message); }
    return;
  }

  const deleteButton = event.target.closest('[data-note-delete]');
  if (deleteButton) {
    event.stopPropagation();
    const row = deleteButton.closest('[data-note-id]');
    const card = deleteButton.closest('[data-video-id]');
    try {
      await libraryRequest(`/api/notes/${row.dataset.noteId}`, {method: 'DELETE'});
      await refreshNotes(card.dataset.videoId);
    } catch (error) { showNoteError(card, error.message); }
    return;
  }

  const addButton = event.target.closest('[data-note-add]');
  if (addButton) {
    const card = addButton.closest('[data-video-id]');
    if (card.querySelector('.note-row.is-new')) return;
    const row = document.createElement('div');
    row.className = 'note-row is-new';
    row.innerHTML = '<textarea class="note-editor" aria-label="新笔记"></textarea>';
    card.querySelector('[data-note-list]').append(row);
    const editor = row.querySelector('textarea');
    editor.addEventListener('blur', () => saveNewNote(card, row, editor), {once: true});
    editor.focus();
    return;
  }

  const rendered = event.target.closest('.note-rendered');
  if (rendered) {
    const row = rendered.closest('[data-note-id]');
    const card = rendered.closest('[data-video-id]');
    if (row.querySelector('textarea')) return;
    const editor = document.createElement('textarea');
    editor.className = 'note-editor';
    editor.value = row.dataset.noteContent || '';
    rendered.replaceWith(editor);
    editor.addEventListener('blur', () => saveExistingNote(card, row, editor), {once: true});
    editor.focus();
  }
});

async function saveNewNote(card, row, editor) {
  const content = editor.value.trim();
  if (!content) { row.remove(); return; }
  try {
    await libraryRequest(`/api/videos/${card.dataset.videoId}/notes`, {method: 'POST', body: {content}});
    await refreshNotes(card.dataset.videoId);
  } catch (error) { showNoteError(card, error.message); editor.addEventListener('blur', () => saveNewNote(card, row, editor), {once: true}); }
}

async function saveExistingNote(card, row, editor) {
  const content = editor.value.trim();
  if (!content) { editor.value = row.dataset.noteContent || ''; }
  try {
    await libraryRequest(`/api/notes/${row.dataset.noteId}`, {method: 'PATCH', body: {content: editor.value}});
    await refreshNotes(card.dataset.videoId);
  } catch (error) { showNoteError(card, error.message); editor.addEventListener('blur', () => saveExistingNote(card, row, editor), {once: true}); }
}

async function refreshNotes(videoId) {
  const data = await libraryRequest(`/api/videos/${videoId}/notes`);
  cardsForVideo(videoId).forEach(card => {
    const list = card.querySelector('[data-note-list]');
    if (!list) return;
    list.replaceChildren(...data.notes.map(note => {
      const row = document.createElement('div');
      row.className = 'note-row';
      row.dataset.noteId = note.id;
      row.dataset.noteContent = note.content;
      row.innerHTML = `<div class="note-main"><div class="note-rendered markdown-note">${note.rendered_html}</div><small>${note.display_updated_at}</small></div><button data-note-delete title="删除笔记" aria-label="删除笔记">×</button>`;
      return row;
    }));
    const count = card.querySelector('[data-note-count]');
    if (count) count.textContent = data.notes.length;
    showNoteError(card, '');
  });
  if (!data.notes.length && document.querySelector('[data-library-view]')?.dataset.libraryView === 'noted') cardsForVideo(videoId).forEach(card => card.remove());
}

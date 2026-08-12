(() => {
  const root = document.querySelector('[data-research-page]');
  const evidenceUI = window.ShiliuEvidenceUI;
  const personalizationUI = window.ShiliuResearchPersonalization;
  if (!root || !evidenceUI || !personalizationUI) return;

  const {element, renderEvidenceCard} = evidenceUI;
  const createForm = root.querySelector('[data-research-create]');
  const taskList = root.querySelector('[data-task-list]');
  const workspace = root.querySelector('[data-task-workspace]');
  const emptyWorkspace = root.querySelector('[data-empty-workspace]');
  const taskContent = root.querySelector('[data-task-content]');
  const taskLoading = root.querySelector('[data-task-loading]');
  const taskError = root.querySelector('[data-task-error]');
  let activeTaskId = root.dataset.initialTaskId || '';
  let current = null;
  let knowledge = null;
  let personalWorkspace = null;
  let personalizationEnabled = true;
  let routingEnabled = true;
  let assistanceEnabled = true;
  let journeyEnabled = true;
  const sessionDismissedAssistance = new Set();
  let pollTimer = null;

  const commandId = prefix => {
    const identity = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `product:${prefix}:${identity}`;
  };
  const lines = value => value.split('\n').map(item => item.trim()).filter(Boolean);
  const errorMessage = data => data?.error?.message || data?.detail || '请求失败，请刷新持久状态后重试。';

  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(errorMessage(data));
    return data;
  };

  const showTaskState = name => {
    taskLoading.hidden = name !== 'loading';
    taskError.hidden = name !== 'error';
    taskContent.hidden = name !== 'content';
  };

  const setActiveTask = taskId => {
    activeTaskId = taskId;
    history.pushState({}, '', `/research/${encodeURIComponent(taskId)}`);
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    loadTask();
    loadList();
  };

  const loadList = async () => {
    try {
      const data = await requestJson('/api/research/product/tasks?limit=30');
      taskList.replaceChildren();
      if (!data.tasks.length) {
        taskList.append(element('p', 'muted', '还没有 Research Task。'));
        return;
      }
      data.tasks.forEach(task => {
        const button = element('button', `research-task-card${task.task_id === activeTaskId ? ' is-active' : ''}`);
        button.type = 'button';
        button.append(
          element('span', 'task-card-state', task.user_completion?.label || task.status_label),
          element('strong', '', task.objective),
          element('span', '', `${task.task_id} · ${task.updated_at}`),
        );
        button.addEventListener('click', () => setActiveTask(task.task_id));
        taskList.append(button);
      });
    } catch (error) {
      taskList.replaceChildren(element('p', 'research-error', error.message));
    }
  };

  const renderAnswer = product => {
    const section = root.querySelector('[data-answer-section]');
    const container = root.querySelector('[data-answer-blocks]');
    const compactContainer = root.querySelector('[data-answer-compact-blocks]');
    container.replaceChildren();
    compactContainer.replaceChildren();
    const numbering = new Map(product.citations.map((item, index) => [item.citation_id, index + 1]));
    (product.answer_blocks || []).forEach(block => {
      const card = element('article', 'research-answer-block');
      card.append(element('span', '', block.text));
      (block.citation_ids || []).forEach(id => {
        const number = numbering.get(id);
        if (!number) return;
        const marker = element('button', 'research-citation-button', `[${number}]`);
        marker.type = 'button';
        marker.addEventListener('click', () => document.getElementById(`research-citation-${number}`)?.scrollIntoView({behavior: 'smooth'}));
        card.append(marker);
      });
      container.append(card);
    });
    section.hidden = !product.answer_blocks.length && !product.limitations.length;
    const limitations = root.querySelector('[data-limitations]');
    container.after(limitations);
    limitations.hidden = !product.limitations.length;
    const list = limitations.querySelector('ul');
    list.replaceChildren(...product.limitations.map(value => element('li', '', value)));
  };

  const renderPersonalization = context => {
    const answerSection = root.querySelector('[data-answer-section]');
    const answerBlocks = root.querySelector('[data-answer-blocks]');
    const limitations = root.querySelector('[data-limitations]');
    const compactDetails = root.querySelector('[data-answer-compact-details]');
    const compactBlocks = root.querySelector('[data-answer-compact-blocks]');
    const detail = personalizationUI.applyAnswerDetail(
      answerBlocks, compactDetails, compactBlocks, context,
    );
    root.querySelector('[data-answer-compact-count]').textContent = String(detail.compactedCount);
    const position = personalizationUI.applyAnswerPresentation(
      answerSection, answerBlocks, limitations, context, compactDetails,
    );
    const status = root.querySelector('[data-personalization-status]');
    const preference = context.preference;
    const focus = context.current_focus;
    if ((context.applied && preference) || context.detail_applied) {
      const effects = [
        ...(context.applied && preference ? [`limitations ${preference.value}`] : []),
        ...(context.detail_applied ? [`detail ${detail.detailLevel}`] : []),
      ];
      status.textContent = `已应用 ${effects.join(' · ')}${focus ? ` · Current Focus: ${focus.topic} (${focus.state})` : ''}`;
    } else {
      status.textContent = `保持 baseline (${position}, ${detail.detailLevel}) · ${(context.reason_codes || []).join(', ')}`;
    }
    root.querySelector('[data-personalization-explanation]').textContent = JSON.stringify({
      policy_version: context.policy_version,
      enabled: context.enabled,
      applied: context.applied,
      effect_scope: context.effect_scope,
      preference: context.preference,
      detail_level: context.detail_level,
      detail_applied: context.detail_applied,
      detail_preference: context.detail_preference,
      detail_reason_codes: context.detail_reason_codes,
      current_focus: context.current_focus,
      reason_codes: context.reason_codes,
      context_hash: context.context_hash,
      authority: context.authority,
    }, null, 2);
  };

  const renderEvidence = product => {
    const section = root.querySelector('[data-evidence-section]');
    const list = root.querySelector('[data-evidence-list]');
    list.replaceChildren();
    product.citations.forEach((citation, index) => {
      const current = citation.currentness === 'current';
      const wrapper = element('div', `research-evidence-card${current ? '' : ' is-stale'}`);
      wrapper.append(element('span', `research-currentness${current ? '' : ' is-stale'}`, citation.currentness));
      wrapper.append(renderEvidenceCard({
        id: `research-citation-${index + 1}`,
        evidenceId: citation.citation_id,
        videoId: citation.video_id,
        eyebrow: `证据 [${index + 1}] · ${citation.source_type}`,
        title: citation.title,
        startTime: citation.start_time,
        endTime: citation.end_time,
        quote: citation.quote_text,
        sourceType: citation.source_type,
        jumpUrl: citation.jump_url,
        metadata: [
          ['Evidence ID', citation.citation_id],
          ['Evidence Use', citation.evidence_use_id],
          ['Source Version', citation.source_version],
          ['Attempt', citation.attempt_id],
        ],
      }));
      list.append(wrapper);
    });
    root.querySelector('[data-evidence-count]').textContent = `${product.citations.length} 条`;
    section.hidden = !product.citations.length;
  };

  const renderDeltas = product => {
    const grid = root.querySelector('[data-delta-grid]');
    grid.replaceChildren();
    const snapshot = product.candidate_deltas;
    if (!snapshot) {
      grid.append(element('p', 'muted', '任务尚未到达需要形成 Candidate Delta 的持久边界。'));
      return;
    }
    snapshot.deltas.forEach(delta => {
      const card = element('article', 'research-delta-card');
      card.append(element('span', 'research-delta-status', 'CANDIDATE ONLY'), element('h4', '', delta.delta_kind));
      if (!delta.items.length) {
        card.append(element('p', '', `空候选：${delta.empty_reason}`));
      } else {
        const list = element('ul');
        delta.items.forEach(item => list.append(element('li', '', item.summary || item.reason_code || JSON.stringify(item))));
        card.append(list);
      }
      card.append(element('p', '', `hash · ${delta.candidate_hash.slice(0, 16)}…`));
      grid.append(card);
    });
  };

  const renderTrace = product => {
    const trace = product.trace;
    const list = root.querySelector('[data-trace-timeline]');
    list.replaceChildren();
    trace.timeline.slice().reverse().forEach(item => {
      const row = element('li');
      const body = element('div');
      body.append(element('strong', '', item.summary));
      const details = Object.keys(item.details).length ? ` · ${JSON.stringify(item.details)}` : '';
      body.append(element('small', '', `${item.created_at}${details}`));
      row.append(element('span', 'trace-sequence', `#${item.sequence}`), body);
      list.append(row);
    });
    root.querySelector('[data-trace-counts]').textContent = `${trace.counts.events} events · ${trace.counts.receipts} receipts`;
    root.querySelector('[data-advanced-trace]').textContent = JSON.stringify({
      checkpoints: trace.checkpoints,
      actions: trace.actions,
      audits: trace.audits,
      receipts: trace.receipts,
      controls: trace.controls,
    }, null, 2);
  };

  const knowledgeAction = async (path, body, statusText) => {
    const status = root.querySelector('[data-knowledge-status]');
    status.textContent = statusText;
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/knowledge${path}`, {
        method: 'POST', body: JSON.stringify(body),
      });
      status.textContent = '已提交并写入持久回执。';
      await loadKnowledge();
      await loadTask();
    } catch (error) { status.textContent = error.message; }
  };

  const submitKnowledgeFeedback = (targetKind, targetId, expectedHash, decision, proposedValue = '') => {
    const note = window.prompt(
      decision === 'helpful' ? '可选：哪里有帮助？' : '可选：哪里需要修正？',
      '',
    );
    if (note === null) return;
    knowledgeAction('/feedback', {
      command_id: commandId(`feedback-${decision}`),
      target_kind: targetKind,
      target_id: targetId,
      decision,
      reason_code: targetKind === 'artifact_route' ? 'route' : 'answer_quality',
      note: note.trim(),
      expected_hash: expectedHash,
      ...(proposedValue ? {candidate_preference: {
        semantic_key: 'answer.presentation.limitations_position',
        proposed_value: proposedValue,
      }} : {}),
    }, '正在记录 advisory Feedback Event…');
  };

  const feedbackControls = (targetKind, targetId, expectedHash) => {
    const controls = element('div', 'research-control-buttons');
    const preferenceLabel = element('label', '', 'Candidate preference');
    const preference = element('select');
    [['', 'No preference hint'], ['before_answer', 'Limitations first'], ['after_answer', 'Limitations after answer']]
      .forEach(([value, label]) => {
        const option = element('option', '', label); option.value = value; preference.append(option);
      });
    preferenceLabel.append(preference);
    controls.append(preferenceLabel);
    [['helpful', 'Helpful'], ['needs_fix', 'Needs fix']].forEach(([decision, label]) => {
      const button = element('button', 'ghost compact-button', label);
      button.type = 'button';
      button.addEventListener('click', () => submitKnowledgeFeedback(
        targetKind, targetId, expectedHash, decision, preference.value,
      ));
      controls.append(button);
    });
    return controls;
  };

  const createPreferenceCandidate = async group => {
    const status = root.querySelector('[data-workspace-status]');
    status.textContent = '正在从 exact Feedback Events 创建 candidate；确认前不会改变产品行为…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/workspace/records`, {
        method: 'POST', body: JSON.stringify({
          command_id: commandId('feedback-preference-candidate'),
          record_kind: 'inferred_candidate',
          semantic_key: group.semanticKey,
          payload: {statement: group.proposedValue},
          source_refs: group.events.slice(0, 32).map(value => ({
            ref_type: 'research_event', ref_id: value.event_id, task_id: activeTaskId,
          })),
          confidence: 1,
          reason: 'explicitly created from compatible exact-target structured Feedback Events',
        }),
      });
      status.textContent = 'Candidate 已创建；必须显式 confirm 才可能影响 Research 展示。';
      await loadPersonalWorkspace();
    } catch (error) { status.textContent = error.message; }
  };

  const renderFeedbackPreferenceCandidates = (observability, target) => {
    const groups = new Map();
    (observability.feedback || []).forEach(value => {
      const preference = value.candidate_preference;
      if (!preference) return;
      const key = `${preference.semantic_key}\u0000${preference.proposed_value}\u0000${value.principal_id || ''}`;
      if (!groups.has(key)) groups.set(key, {
        semanticKey: preference.semantic_key,
        proposedValue: preference.proposed_value,
        principalId: value.principal_id || '',
        events: [],
      });
      groups.get(key).events.push(value);
    });
    groups.forEach(group => {
      if (group.events.length < 2) return;
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('strong', '', `Candidate · ${group.semanticKey} = ${group.proposedValue}`),
        element('small', '', `${group.events.length} compatible Feedback Events · principal ${group.principalId}`),
      );
      const button = element('button', 'ghost compact-button', 'Create candidate for review');
      button.type = 'button'; button.addEventListener('click', () => createPreferenceCandidate(group));
      card.append(button); target.append(card);
    });
  };

  const reviewCandidate = (candidate, decision) => {
    let editedClaim = null;
    if (decision === 'edit') {
      editedClaim = window.prompt('编辑会创建新的 needs_revalidation Candidate；原 Candidate 不会被改写。', candidate.claim);
      if (editedClaim === null || !editedClaim.trim()) return;
      editedClaim = editedClaim.trim();
    }
    knowledgeAction(`/candidates/${encodeURIComponent(candidate.candidate_id)}/review`, {
      command_id: commandId(`candidate-${decision}`), decision,
      expected_state_version: candidate.state_version,
      reason: `local operator ${decision}`,
      ...(editedClaim ? {edited_claim: editedClaim} : {}),
    }, '正在提交 Candidate 审查…');
  };

  const proposeFactUpdate = (fact, kind) => {
    let proposedClaim = null;
    if (['user_correction', 'supersede'].includes(kind)) {
      proposedClaim = window.prompt('修正必须仍可由当前 Evidence 机械支撑；否则会保持 needs_revalidation。', fact.claim);
      if (proposedClaim === null || !proposedClaim.trim()) return;
      proposedClaim = proposedClaim.trim();
    }
    knowledgeAction(`/facts/${encodeURIComponent(fact.fact_id)}/updates`, {
      command_id: commandId(`fact-${kind}`), kind,
      expected_fact_state_version: fact.fact_state_version,
      evidence_use_ids: fact.citations.map(value => value.evidence_use_id),
      reason: `local operator ${kind}`,
      ...(proposedClaim ? {proposed_claim: proposedClaim} : {}),
    }, '正在创建 durable update Candidate…');
  };

  const reviewUpdate = (candidate, decision) => {
    const state = (knowledge.fact_states || []).find(value => value.fact_id === candidate.fact_id);
    if (!state) return;
    let editedClaim = null;
    if (decision === 'edit') {
      editedClaim = window.prompt('编辑会创建 needs_revalidation 子 Candidate。', candidate.proposed_claim || '');
      if (editedClaim === null || !editedClaim.trim()) return;
    }
    knowledgeAction(`/updates/${encodeURIComponent(candidate.update_candidate_id)}/review`, {
      command_id: commandId(`update-${decision}`), decision,
      expected_candidate_version: candidate.state_version,
      expected_fact_state_version: state.state_version,
      reason: `local operator ${decision}`,
      ...(editedClaim ? {edited_claim: editedClaim.trim()} : {}),
    }, '正在审查知识更新…');
  };

  const inspectPageHistory = async (page, target) => {
    const status = root.querySelector('[data-knowledge-status]');
    status.textContent = '正在读取 immutable Page history/diff…';
    try {
      const historyData = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/knowledge/pages/${encodeURIComponent(page.page_id)}/history`);
      let diffLines = [];
      if (page.version > 1) {
        const diffData = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/knowledge/pages/${encodeURIComponent(page.page_id)}/diff?from_version=1&to_version=${encodeURIComponent(page.version)}`);
        diffLines = diffData.diff.lines;
      }
      target.textContent = JSON.stringify({
        current_version: historyData.history.current_version,
        published_version: historyData.history.published_version,
        revisions: historyData.history.revisions.map(value => ({version: value.version, kind: value.revision_kind, id: value.page_revision_id})),
        diff_from_v1: diffLines,
      }, null, 2);
      target.hidden = false; status.textContent = '已读取 history/diff；它们是 SQLite revision 的派生视图。';
    } catch (error) { status.textContent = error.message; }
  };

  const renderKnowledge = workspaceData => {
    knowledge = workspaceData;
    const closeout = knowledge.closeout || {};
    const observability = closeout.observability || {counts: {}, feedback: []};
    const closeoutList = root.querySelector('[data-knowledge-closeout]');
    closeoutList.replaceChildren(
      element('h4', '', 'V5-B · Stage 5 product completion'),
      element('p', 'muted', 'Relations 只用于 navigation；Feedback 只写 Event + Receipt，均不会改变检索、route 或发布 authority。'),
      element('small', '', `Derived observability · ${observability.counts.events || 0} events · ${observability.counts.receipts || 0} receipts · ${observability.counts.build_runs || 0} builds · ${observability.counts.artifact_routes || 0} route records · ${observability.counts.feedback || 0} feedback`),
    );
    const paths = closeout.product_paths || {};
    if (paths.reuse_first) closeoutList.append(element('p', 'research-currentness', `Reuse-first · ${paths.reuse_first.route} · ${paths.reuse_first.status}`));
    if (paths.research_change) closeoutList.append(element('p', 'research-currentness', `Research-change · ${paths.research_change.route} · ${paths.research_change.status}`));
    renderFeedbackPreferenceCandidates(observability, closeoutList);
    const candidateList = root.querySelector('[data-knowledge-candidates]');
    candidateList.replaceChildren(element('h4', '', `Candidate · ${knowledge.candidates.length}`));
    knowledge.candidates.forEach(candidate => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${candidate.status === 'pending_review' ? '' : ' is-stale'}`, candidate.status),
        element('p', 'research-knowledge-claim', candidate.claim),
        element('small', '', `${candidate.candidate_id} · v${candidate.state_version}`),
      );
      candidate.evidence.forEach(value => card.append(element(
        'small', value.current_outcome === 'current' ? 'research-currentness' : 'research-currentness is-stale',
        `Evidence · ${value.current_outcome} · ${value.title || value.reason_code}`,
      )));
      if (['pending_review', 'needs_revalidation'].includes(candidate.status)) {
        const actions = element('div', 'research-control-buttons');
        if (candidate.status === 'pending_review') {
          const accept = element('button', 'ghost', 'Accept → Fact');
          accept.type = 'button';
          accept.addEventListener('click', () => reviewCandidate(candidate, 'accept'));
          actions.append(accept);
        }
        const reject = element('button', 'ghost is-destructive', 'Reject');
        reject.type = 'button';
        reject.addEventListener('click', () => reviewCandidate(candidate, 'reject'));
        const edit = element('button', 'ghost', 'Edit as new Candidate');
        edit.type = 'button';
        edit.addEventListener('click', () => reviewCandidate(candidate, 'edit'));
        actions.append(reject, edit);
        card.append(actions);
      }
      candidateList.append(card);
    });
    if (!knowledge.candidates.length) candidateList.append(element('p', 'muted', '尚未接收 KnowledgeDelta Candidate。'));

    const factList = root.querySelector('[data-knowledge-facts]');
    const factHeading = element('div', 'research-section-heading');
    factHeading.append(element('h4', '', `Accepted Fact · ${knowledge.facts.length}`));
    const currentFacts = knowledge.facts.filter(fact => fact.is_current_revision && fact.lifecycle_status === 'current');
    if (currentFacts.length) {
      const build = element('button', 'ghost compact-button', '构建确定性 Artifact');
      build.type = 'button';
      build.addEventListener('click', () => knowledgeAction('/artifacts', {
        command_id: commandId('artifact-build'),
        fact_revision_ids: currentFacts.map(fact => fact.fact_revision_id),
      }, '正在同步构建 Artifact…'));
      factHeading.append(build);
    }
    factList.replaceChildren(factHeading);
    knowledge.facts.forEach(fact => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${fact.currentness_status === 'current' && fact.lifecycle_status === 'current' ? '' : ' is-stale'}`, `${fact.lifecycle_status} · ${fact.currentness_status}`),
        element('p', 'research-knowledge-claim', fact.claim),
        element('small', '', `revision ${fact.revision}${fact.is_current_revision ? ' · current head' : ' · history'}`),
      );
      fact.citations.forEach(citation => {
        const citationRow = element('div', 'research-citation-drilldown');
        citationRow.append(element('span', '', `${citation.current_outcome} · ${citation.title} · ${citation.quote}`));
        if (citation.jump_url) {
          const jump = element('a', '', '时间点播放');
          jump.href = citation.jump_url; jump.target = '_blank'; jump.rel = 'noopener noreferrer';
          citationRow.append(jump);
        }
        const transcript = element('a', '', '字幕原文');
        transcript.href = citation.transcript_href; transcript.target = '_blank';
        citationRow.append(transcript); card.append(citationRow);
      });
      if (fact.is_current_revision && fact.lifecycle_status === 'current') {
        const actions = element('div', 'research-control-buttons');
        [['user_correction', '修正'], ['retire', 'Retire'], ['supersede', 'Supersede']].forEach(([kind, label]) => {
          const button = element('button', kind === 'retire' ? 'ghost is-destructive' : 'ghost', label);
          button.type = 'button'; button.addEventListener('click', () => proposeFactUpdate(fact, kind)); actions.append(button);
        });
        card.append(actions);
      }
      factList.append(card);
    });

    const artifactList = root.querySelector('[data-knowledge-artifacts]');
    artifactList.replaceChildren(element('h4', '', `Artifact revision · ${knowledge.artifacts.length}`));
    knowledge.artifacts.forEach(artifact => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${artifact.currentness_status === 'current' ? '' : ' is-stale'}`, artifact.currentness_status),
        element('strong', '', artifact.topic), element('small', '', artifact.artifact_revision_id),
      );
      if (artifact.currentness_status === 'current') {
        const build = element('button', 'ghost compact-button', '构建首版 Topic Page');
        build.type = 'button';
        build.addEventListener('click', () => knowledgeAction('/pages', {
          command_id: commandId('page-build'), artifact_revision_id: artifact.artifact_revision_id,
        }, '正在同步构建首版 Topic Page…'));
        card.append(build);
      }
      artifactList.append(card);
    });

    const pageList = root.querySelector('[data-knowledge-pages]');
    pageList.replaceChildren(element('h4', '', `Topic Page · ${knowledge.pages.length}`));
    knowledge.pages.forEach(page => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${page.currentness_status === 'current' ? '' : ' is-stale'}`, `${page.review_status} · ${page.currentness_status}`),
        element('strong', '', page.title),
        element('small', '', `${page.page_revision_id} · version ${page.version} · published ${page.published_version || 'none'}`),
      );
      (page.body.facts || []).forEach(fact => card.append(element('p', 'research-knowledge-claim', fact.claim)));
      const relations = page.relations || {items: [], total: 0, truncated: false};
      relations.items.forEach(relation => {
        const relationRow = element('div', 'research-citation-drilldown');
        const target = element('a', '', `${relation.kind} → ${relation.target.title}`);
        target.href = `#knowledge-page-${encodeURIComponent(relation.target.page_id)}`;
        relationRow.append(target, element('span', '', ` · ${relation.reason}`));
        (relation.supporting_facts || []).flatMap(fact => fact.citations || []).slice(0, 2).forEach(citation => {
          const drill = element('a', '', 'L1');
          drill.href = citation.transcript_href; drill.target = '_blank'; relationRow.append(drill);
        });
        card.append(relationRow);
      });
      if (relations.truncated) card.append(element('small', 'muted', `显示 ${relations.items.length}/${relations.total} 条 bounded relations`));
      if (page.review_status === 'draft') {
        const actions = element('div', 'research-control-buttons');
        ['publish', 'return'].forEach(decision => {
          const button = element('button', decision === 'return' ? 'ghost is-destructive' : 'ghost', decision === 'publish' ? 'Publish' : 'Return');
          button.type = 'button';
          button.addEventListener('click', () => knowledgeAction(`/pages/${encodeURIComponent(page.page_id)}/review`, {
            command_id: commandId(`page-${decision}`), decision,
            expected_version: page.version, reason: `local operator ${decision}`,
          }, '正在提交 Page 审查…'));
          actions.append(button);
        });
        card.append(actions);
      }
      const lifecycle = element('div', 'research-control-buttons');
      const edit = element('button', 'ghost', 'Edit draft');
      edit.type = 'button'; edit.addEventListener('click', () => {
        const annotation = window.prompt('添加或更新用户注释；Fact blocks 保持引用既有 grounded revision。', page.body.user_annotation || '');
        if (annotation === null) return;
        knowledgeAction(`/pages/${encodeURIComponent(page.page_id)}/edit`, {
          command_id: commandId('page-edit'), expected_version: page.version,
          annotation, reason: 'local operator edit',
        }, '正在创建新的 Page draft revision…');
      });
      const revert = element('button', 'ghost', 'Revert to v1');
      revert.type = 'button'; revert.disabled = page.version === 1;
      revert.addEventListener('click', () => knowledgeAction(`/pages/${encodeURIComponent(page.page_id)}/revert`, {
        command_id: commandId('page-revert'), expected_version: page.version,
        target_version: 1, reason: 'local operator revert',
      }, '正在以新 revision 执行 revert…'));
      const exportButton = element('button', 'ghost', 'Export Markdown');
      exportButton.type = 'button'; exportButton.addEventListener('click', () => knowledgeAction('/exports', {
        command_id: commandId('page-export'), page_revision_id: page.page_revision_id,
        export_format: 'markdown',
      }, '正在导出 revision-ID/content-hash addressed Markdown…'));
      const historyOutput = element('pre', 'research-advanced-trace'); historyOutput.hidden = true;
      const historyButton = element('button', 'ghost', 'History / diff'); historyButton.type = 'button';
      historyButton.addEventListener('click', () => inspectPageHistory(page, historyOutput));
      lifecycle.append(edit, revert, historyButton, exportButton);
      card.id = `knowledge-page-${page.page_id}`;
      card.append(lifecycle, feedbackControls('topic_page_revision', page.page_revision_id, page.content_hash), historyOutput);
      pageList.append(card);
    });

    const updateList = root.querySelector('[data-knowledge-updates]');
    updateList.replaceChildren(element('h4', '', `Update Candidate · ${(knowledge.update_candidates || []).length}`));
    (knowledge.update_candidates || []).forEach(candidate => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${candidate.status === 'pending_review' ? '' : ' is-stale'}`, `${candidate.kind} · ${candidate.status}`),
        element('p', 'research-knowledge-claim', candidate.proposed_claim || candidate.source_fact_revision_id),
        element('small', '', `${candidate.update_candidate_id} · validator ${candidate.validator_status}`),
      );
      if (['pending_review', 'needs_revalidation'].includes(candidate.status)) {
        const actions = element('div', 'research-control-buttons');
        if (candidate.status === 'pending_review') {
          const accept = element('button', 'ghost', 'Accept update'); accept.type = 'button';
          accept.addEventListener('click', () => reviewUpdate(candidate, 'accept')); actions.append(accept);
        }
        const reject = element('button', 'ghost is-destructive', 'Reject'); reject.type = 'button';
        reject.addEventListener('click', () => reviewUpdate(candidate, 'reject'));
        const edit = element('button', 'ghost', 'Edit as new'); edit.type = 'button';
        edit.addEventListener('click', () => reviewUpdate(candidate, 'edit')); actions.append(reject, edit); card.append(actions);
      }
      updateList.append(card);
    });

    const operationList = root.querySelector('[data-knowledge-operations]');
    operationList.replaceChildren(element('h4', '', `Durable operation · ${(knowledge.operations || []).length}`));
    (knowledge.operations || []).forEach(operation => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${operation.status === 'succeeded' ? '' : ' is-stale'}`, `${operation.kind} · ${operation.status}`),
        element('small', '', `${operation.operation_id} · attempt ${operation.attempt_count}/${operation.max_attempts}`),
      );
      if (['pending', 'retry_wait'].includes(operation.status) && operation.kind === 'refresh_knowledge') {
        const run = element('button', 'ghost', operation.status === 'pending' ? 'Run refresh' : 'Safe retry'); run.type = 'button';
        run.addEventListener('click', () => knowledgeAction(`/operations/${encodeURIComponent(operation.operation_id)}/run`, {
          command_id: commandId('operation-run'), claimant_id: 'local_ui',
        }, '正在运行受 fence 保护的 durable refresh…')); card.append(run);
      }
      if (operation.status === 'needs_user') {
        const retry = element('button', 'ghost', 'Resolve → retry'); retry.type = 'button';
        retry.addEventListener('click', () => knowledgeAction(`/operations/${encodeURIComponent(operation.operation_id)}/resolve`, {
          command_id: commandId('operation-resolve-retry'), action: 'retry',
          expected_claim_generation: operation.claim_generation, reason: 'local operator resolved blocker',
        }, '正在持久记录 needs-user resolution…')); card.append(retry);
      }
      if (['pending', 'retry_wait', 'needs_user', 'dead_letter'].includes(operation.status)) {
        const cancel = element('button', 'ghost is-destructive', 'Cancel operation'); cancel.type = 'button';
        cancel.addEventListener('click', () => knowledgeAction(`/operations/${encodeURIComponent(operation.operation_id)}/resolve`, {
          command_id: commandId('operation-cancel'), action: 'cancel',
          expected_claim_generation: operation.claim_generation, reason: 'local operator cancelled bounded operation',
        }, '正在持久取消 operation…')); card.append(cancel);
      }
      if (operation.error_detail) card.append(element('p', 'muted', `${operation.error_class} · ${operation.error_code} · ${operation.error_detail}`));
      operationList.append(card);
    });

    const routeList = root.querySelector('[data-knowledge-routes]');
    routeList.replaceChildren(element('h4', '', `ArtifactRoute · ${(knowledge.artifact_routes || []).length}`));
    (knowledge.artifact_routes || []).forEach(route => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${route.status === 'completed' ? '' : ' is-stale'}`, `${route.final_route || route.recommended_route} · ${route.status}`),
        element('p', 'research-knowledge-claim', route.query.query),
        element('small', '', `${route.route_id} · v${route.version} · authority ${route.expected_authority_hash.slice(0, 16)}…`),
      );
      const openCount = route.retrieval.open_corpus?.results?.length || 0;
      card.append(element('small', '', `Artifact candidates ${(route.gates || []).length} · independent open corpus ${openCount}`));
      (route.gates || []).slice(0, 3).forEach(gate => {
        card.append(element('p', 'muted', `${gate.artifact_revision_id} · scope ${gate.scope_status} · current ${gate.currentness_status} · citations ${gate.citation_status} · coverage ${gate.completeness_status} → ${gate.candidate_route}`));
        if ((gate.missing_aspects || []).length) card.append(element('small', 'research-currentness is-stale', `gaps · ${gate.missing_aspects.join(' / ')}`));
        (gate.facts || []).flatMap(fact => fact.citations || []).slice(0, 3).forEach(citation => {
          const drill = element('a', '', `L1 · ${citation.evidence_id} · ${citation.start_time}s`);
          drill.href = citation.transcript_href; drill.target = '_blank'; card.append(drill);
        });
      });
      if (route.record_kind === 'assessment') {
        const actions = element('div', 'research-control-buttons');
        const order = ['direct_reuse', 'incremental_refresh', 'research_seed'];
        const minimum = order.indexOf(route.recommended_route);
        order.slice(minimum).forEach(value => {
          const button = element('button', 'ghost', value === route.recommended_route ? `Proceed · ${value}` : `Safer · ${value}`);
          button.type = 'button'; button.addEventListener('click', () => knowledgeAction(`/routes/${encodeURIComponent(route.route_id)}/proceed`, {
            command_id: commandId(`route-${value}`), action: 'confirm', expected_version: route.version,
            route: value, reason: value === route.recommended_route ? 'accepted recommendation' : 'selected safer route',
          }, '正在持久确认 ArtifactRoute 与 authority fence…')); actions.append(button);
        });
        card.append(actions);
      }
      if (route.continuation_task_id) {
        const child = element('a', '', `Continuation Task · ${route.continuation_task_id}`);
        child.href = `/research/${encodeURIComponent(route.continuation_task_id)}`; card.append(child);
      }
      if (route.outcome_artifact_revision_id) card.append(element('small', '', `Outcome Artifact · ${route.outcome_artifact_revision_id}`));
      if (Object.keys(route.contribution || {}).length) card.append(element('pre', 'research-advanced-trace', JSON.stringify(route.contribution, null, 2)));
      card.append(feedbackControls('artifact_route', route.record_id, route.expected_authority_hash));
      routeList.append(card);
    });
  };

  async function loadKnowledge() {
    if (!activeTaskId) return;
    try {
      const data = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/knowledge`);
      renderKnowledge(data.workspace);
    } catch (error) {
      root.querySelector('[data-knowledge-status]').textContent = error.message;
    }
  }

  const workspacePayload = (kind, semanticKey, value, sourceRefs) => {
    if (kind === 'explicit_memory') return {key: semanticKey, value};
    if (kind === 'inferred_candidate') return {statement: value};
    if (kind === 'focus_state') return {topic: semanticKey, state: value};
    if (kind === 'progress_observation') return {
      topic: semanticKey, state: value, user_asserted: sourceRefs.length === 0,
    };
    if (kind === 'corpus_observation') return {observation_type: 'topic', value};
    return {
      observed_pattern: value,
      outcome: 'observed',
      environment_fingerprint: 'local-ui-v1',
    };
  };

  const decideWorkspaceRecord = async (record, action) => {
    const status = root.querySelector('[data-workspace-status]');
    let replacementPayload;
    let requestAction = action;
    let reason = `local operator ${action}`;
    if (action === 'restore') {
      const prior = record.history.length > 1 ? record.history[record.history.length - 2] : null;
      if (!prior) { status.textContent = '没有可恢复的历史 revision。'; return; }
      replacementPayload = prior.payload;
      requestAction = 'correct';
      reason = `restore_previous_value:v${prior.version}`;
    }
    if (action === 'correct') {
      const replacement = window.prompt('Correction 会追加 immutable revision。请输入完整 JSON payload。', JSON.stringify(record.payload));
      if (replacement === null) return;
      try { replacementPayload = JSON.parse(replacement); }
      catch (_error) { status.textContent = 'Correction payload 必须是 JSON object。'; return; }
    }
    if (action === 'diagnose') {
      const diagnosis = window.prompt('Diagnosis 会保留 observed payload 与 Trace lineage。', '{"cause":""}');
      if (diagnosis === null) return;
      try { replacementPayload = JSON.parse(diagnosis); }
      catch (_error) { status.textContent = 'Diagnosis 必须是 JSON object。'; return; }
    }
    status.textContent = `正在追加 ${requestAction} decision…`;
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/workspace/records/${encodeURIComponent(record.record_id)}/decisions`, {
        method: 'POST', body: JSON.stringify({
          command_id: commandId(`workspace-${action}`), action: requestAction,
          expected_version: record.version, reason,
          ...(replacementPayload ? {replacement_payload: replacementPayload} : {}),
        }),
      });
      status.textContent = 'Decision 已追加；旧 revision 与 source boundary 保留。';
      await loadPersonalWorkspace();
    } catch (error) { status.textContent = error.message; }
  };

  const renderPersonalWorkspace = value => {
    personalWorkspace = value;
    renderPersonalization(value.personalization_context);
    renderRouteRecommendation(value.route_recommendation);
    renderKnowledgeAssistance(value.knowledge_assistance);
    renderIntegratedJourney(value.integrated_journey);
    const list = root.querySelector('[data-workspace-records]');
    list.replaceChildren(element('h4', '', `WorkspaceRecord · ${value.records.length}`));
    value.records.forEach(record => {
      const card = element('article', 'research-knowledge-card');
      card.append(
        element('span', `research-currentness${['current', 'confirmed'].includes(record.effective_status) ? '' : ' is-stale'}`, `${record.record_kind} · ${record.effective_status}`),
        element('strong', '', record.semantic_key),
        element('small', '', `${record.authority_class} · v${record.version} · answer effect ${record.product_behavior_effect ? 'presentation' : 'false'} · route effect ${record.route_recommendation_effect ? 'advisory only' : 'false'}`),
        element('pre', 'research-advanced-trace', JSON.stringify(record.payload, null, 2)),
      );
      if (record.confidence !== null) card.append(element('small', '', `confidence ${record.confidence}`));
      if (record.expires_at) card.append(element('small', '', `expiry ${record.expires_at}`));
      record.source_refs.forEach(ref => {
        const source = element('a', '', `${ref.ref_type} · ${ref.ref_id}`);
        source.href = ref.href; card.append(source);
      });
      const history = element('details');
      history.append(element('summary', '', `Immutable history · ${record.history.length}`));
      history.append(element('pre', 'research-advanced-trace', JSON.stringify(record.history, null, 2)));
      card.append(history);
      if (record.allowed_actions.length) {
        const actions = element('div', 'research-control-buttons');
        record.allowed_actions.forEach(action => {
          const button = element('button', ['reject', 'tombstone', 'invalidate'].includes(action) ? 'ghost is-destructive' : 'ghost', action);
          button.type = 'button'; button.addEventListener('click', () => decideWorkspaceRecord(record, action)); actions.append(button);
        });
        if (record.allowed_actions.includes('correct') && record.history.length > 1) {
          const restore = element('button', 'ghost', 'restore previous as new revision');
          restore.type = 'button'; restore.addEventListener('click', () => decideWorkspaceRecord(record, 'restore')); actions.append(restore);
        }
        card.append(actions);
      }
      list.append(card);
    });
    if (!value.records.length) list.append(element('p', 'muted', '当前筛选下没有 WorkspaceRecord。'));
  };

  const renderIntegratedJourney = context => {
    const status = root.querySelector('[data-journey-status]');
    const explanation = root.querySelector('[data-journey-explanation]');
    const steps = root.querySelector('[data-journey-steps]');
    steps.replaceChildren();
    if (!context) {
      status.textContent = 'Journey composition 未启用；各 consumer 保持自身 baseline。';
      explanation.textContent = '';
      return;
    }
    status.textContent = `${context.enabled ? 'read-only composition' : 'session all-off'} · ${context.journey_hash.slice(0, 12)} · execution false`;
    const labels = {answer: 'Answer', search: 'Search', routing: 'Next path', assistance: 'Progress & Assistance'};
    Object.entries(context.steps).forEach(([name, step]) => {
      const link = element('a', 'research-journey-step');
      link.href = step.href;
      link.append(
        element('strong', '', labels[name] || name),
        element('small', '', step.status),
        element('code', '', step.context_hash ? step.context_hash.slice(0, 12) : 'no execution context'),
      );
      steps.append(link);
    });
    explanation.textContent = JSON.stringify(context, null, 2);
  };

  const durableDismissAssistance = async card => {
    if (!card.dismiss_control) return;
    const status = root.querySelector('[data-assistance-status]');
    const expiry = root.querySelector('[data-assistance-dismiss-expiry]').value;
    status.textContent = '正在追加 exact-boundary dismiss decision…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/workspace/records`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('assistance-dismiss'),
          ...card.dismiss_control,
          reason: 'explicit durable dismiss from bounded assistance panel',
          ...(expiry ? {expires_at: new Date(expiry).toISOString()} : {}),
        }),
      });
      status.textContent = '已追加 durable dismiss；历史与 exact source boundary 保留。';
      await loadPersonalWorkspace();
    } catch (error) { status.textContent = error.message; }
  };

  const renderKnowledgeAssistance = context => {
    const status = root.querySelector('[data-assistance-status]');
    const explanation = root.querySelector('[data-assistance-explanation]');
    const grid = root.querySelector('[data-assistance-cards]');
    grid.replaceChildren();
    if (!context) {
      status.textContent = 'Assistance projection 未启用；baseline 保持不变。';
      explanation.textContent = '';
      return;
    }
    status.textContent = `${context.status} · ${context.context_hash.slice(0, 12)} · execution / notification authority false`;
    explanation.textContent = JSON.stringify(context, null, 2);
    Object.entries(context.lanes).forEach(([name, lane]) => {
      const section = element('section', 'research-assistance-lane');
      section.append(element('h4', '', `${name} · ${lane.status}`));
      lane.cards.filter(card => !sessionDismissedAssistance.has(card.candidate_id)).forEach(card => {
        const article = element('article', 'research-knowledge-card');
        article.append(
          element('span', 'research-currentness', card.mastery ? 'explicit mastery' : card.kind),
          element('strong', '', card.title),
          element('p', 'muted', card.explanation),
          element('code', '', card.candidate_id),
        );
        if (card.dismiss_control) {
          const controls = element('div', 'research-control-buttons');
          const sessionButton = element('button', 'ghost compact-button', '本次 session 隐藏');
          sessionButton.type = 'button';
          sessionButton.addEventListener('click', () => {
            sessionDismissedAssistance.add(card.candidate_id);
            renderKnowledgeAssistance(context);
          });
          const durableButton = element('button', 'ghost compact-button', 'Durable dismiss');
          durableButton.type = 'button';
          durableButton.addEventListener('click', () => durableDismissAssistance(card));
          controls.append(sessionButton, durableButton);
          article.append(controls);
        }
        section.append(article);
      });
      if (section.children.length === 1) section.append(element('p', 'muted', lane.reason_codes.join(' / ')));
      grid.append(section);
    });
  };

  const renderRouteRecommendation = context => {
    const status = root.querySelector('[data-routing-status]');
    const explanation = root.querySelector('[data-routing-explanation]');
    const cta = root.querySelector('[data-routing-cta]');
    cta.replaceChildren();
    if (!context) {
      status.textContent = 'Routing projection 未启用；现有选择保持不变。';
      explanation.textContent = '';
      return;
    }
    const target = context.recommendation;
    const path = target?.path ? ` · ${target.path}` : '';
    status.textContent = `${context.status}${path} · ${context.reason_codes.join(' / ')} · execution authority false`;
    explanation.textContent = JSON.stringify(context, null, 2);
    if (!target?.cta) return;
    if (target.cta.kind === 'prefill_ask' || target.cta.kind === 'inspect_video_transcript') {
      const link = element('a', 'ghost compact-button', target.cta.kind === 'prefill_ask' ? '打开已预填 Ask（仍需显式提交）' : '检查 exact video transcript');
      link.href = target.cta.href;
      cta.append(link);
      return;
    }
    const focus = element('button', 'ghost compact-button', target.cta.kind === 'focus_artifact_route' ? '聚焦现有 ArtifactRoute control' : '聚焦现有 Research control');
    focus.type = 'button';
    focus.addEventListener('click', () => {
      const control = target.cta.kind === 'focus_artifact_route'
        ? root.querySelector('[data-artifact-route-form] input[name="route_query"]')
        : root.querySelector('[data-control-buttons] button, [data-research-create] textarea');
      control?.scrollIntoView({behavior: 'smooth', block: 'center'});
      control?.focus({preventScroll: true});
    });
    cta.append(focus);
  };

  async function loadPersonalWorkspace() {
    if (!activeTaskId) return;
    const params = new URLSearchParams();
    const kind = root.querySelector('[data-workspace-kind-filter]').value;
    const status = root.querySelector('[data-workspace-status-filter]').value;
    if (kind) params.set('record_kind', kind);
    if (status) params.set('status', status);
    if (!personalizationEnabled) params.set('personalization_enabled', 'false');
    params.set('routing_enabled', String(routingEnabled));
    params.set('assistance_enabled', String(assistanceEnabled));
    params.set('journey_enabled', String(journeyEnabled));
    const baselineSnapshot = Number(root.querySelector('[data-assistance-baseline-snapshot]').value);
    const currentSnapshot = Number(root.querySelector('[data-assistance-current-snapshot]').value);
    if (Number.isInteger(baselineSnapshot) && baselineSnapshot > 0) params.set('baseline_snapshot_id', String(baselineSnapshot));
    if (Number.isInteger(currentSnapshot) && currentSnapshot > 0) params.set('current_snapshot_id', String(currentSnapshot));
    const explicitPath = root.querySelector('[data-routing-explicit-path]').value;
    if (explicitPath) params.set('current_explicit_path', explicitPath);
    params.set('allow_provider_answer', String(root.querySelector('[data-routing-provider-permission]').checked));
    params.set('allow_high_cost_or_durable', String(root.querySelector('[data-routing-cost-permission]').checked));
    params.set('allow_manual_asr', String(root.querySelector('[data-routing-asr-permission]').checked));
    const videoId = Number(root.querySelector('[data-routing-video-id]').value);
    if (Number.isInteger(videoId) && videoId > 0) params.set('asr_video_id', String(videoId));
    try {
      const suffix = params.toString() ? `?${params.toString()}` : '';
      const data = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/workspace${suffix}`);
      renderPersonalWorkspace(data.workspace);
    } catch (error) { root.querySelector('[data-workspace-status]').textContent = error.message; }
  }

  const executeControl = async kind => {
    const context = current.control.action_context;
    if (kind === 'cancel' && !window.confirm('取消会形成持久终态；未知外部副作用会进入 cancel-pending。继续吗？')) return;
    const status = root.querySelector('[data-control-status]');
    status.textContent = '正在提交持久控制命令…';
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/control`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId(kind),
          kind,
          expected_state_version: context.expected_state_version,
          expected_checkpoint_id: context.expected_checkpoint_id,
          expected_control_generation: context.expected_control_generation,
          reason: `product ${kind}`,
        }),
      });
      status.textContent = '已提交；正在读取新的持久状态。';
      await loadTask();
    } catch (error) {
      status.textContent = `${error.message} 请刷新后重试。`;
    }
  };

  const runTask = async () => {
    const status = root.querySelector('[data-control-status]');
    status.textContent = current?.user_completion?.product_execution === 'receipt_bound_provider'
      ? '正在沿已保存状态继续模型研究…'
      : '正在继续本地受限研究…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/run`, {
        method: 'POST', body: JSON.stringify({command_id: commandId('run')}),
      });
      await loadTask();
    } catch (error) { status.textContent = error.message; }
  };

  const deriveTask = async kind => {
    const context = current.control.action_context;
    if (!context.expected_checkpoint_id) return;
    const label = kind === 'branch' ? 'Branch' : 'Replay';
    const confirmed = window.confirm(
      `${label} 会永久创建一个新的派生 Research Task，并保留不可变 lineage；取消不会创建记录。确认继续吗？`,
    );
    if (!confirmed) return;
    try {
      const data = await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/derivations`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId(kind), kind,
          source_checkpoint_id: context.expected_checkpoint_id,
          durable_effect_confirmed: true,
        }),
      });
      setActiveTask(data.outcome.task_id);
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const retryTask = async () => {
    try {
      if (current.user_completion.product_execution === 'receipt_bound_provider') {
        const data = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/retry`, {
          method: 'POST',
          body: JSON.stringify({command_id: commandId('provider-retry')}),
        });
        setActiveTask(data.outcome.task_id);
        return;
      }
      const data = await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/commands`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('retry'), kind: 'retry',
          objective: current.goal.objective,
          success_constraints: current.goal.success_constraints,
          evidence_policy: {authority: 'live_current_exact_replay'},
        }),
      });
      setActiveTask(data.outcome.task_id);
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const resolveEffect = async effect => {
    if (!effect || effect.status !== 'unknown') return;
    const confirmed = window.confirm(
      `确认将 SideEffect ${effect.side_effect_id}（${effect.effect_kind}）记录为失败吗？此决定不可撤销。`,
    );
    if (!confirmed) return;
    const context = current.control.action_context;
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/side-effects/resolve`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('resolve'), side_effect_id: effect.side_effect_id,
          expected_state_version: context.expected_state_version,
          expected_control_generation: context.expected_control_generation,
          resolution: 'confirmed_failed',
          reason: 'product operator confirmed external action failed',
        }),
      });
      await loadTask();
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  };

  const renderControls = product => {
    const container = root.querySelector('[data-control-buttons]');
    container.replaceChildren();
    const labels = {run: '继续安全运行', interrupt: '中断', resume: '恢复', cancel: '取消', derive: '派生', retry: '创建重试 Task'};
    product.control.allowed_operations.forEach(operation => {
      if (operation === 'derive') {
        ['branch', 'replay'].forEach(kind => {
          const button = element('button', 'ghost', kind === 'branch' ? '创建 Branch' : '创建 Replay');
          button.type = 'button';
          button.addEventListener('click', () => deriveTask(kind));
          container.append(button);
        });
        return;
      }
      const button = element('button', operation === 'cancel' ? 'ghost is-destructive' : 'ghost', labels[operation] || operation);
      button.type = 'button';
      button.addEventListener('click', () => operation === 'run' ? runTask() : operation === 'retry' ? retryTask() : executeControl(operation));
      container.append(button);
    });
    if (!container.children.length) container.append(element('p', 'muted', '当前没有可安全执行的操作。'));
  };

  const renderEffects = product => {
    const panel = root.querySelector('[data-effect-panel]');
    const list = root.querySelector('[data-effect-list]');
    const effects = product.control.unresolved_side_effects;
    panel.hidden = !effects.length;
    list.replaceChildren();
    effects.forEach(effect => {
      const card = element('article', 'research-effect-card');
      card.dataset.sideEffectId = effect.side_effect_id;
      card.append(
        element('strong', '', effect.effect_kind),
        element('code', '', effect.side_effect_id),
        element('span', 'research-currentness is-stale', `状态 · ${effect.status}`),
      );
      if (effect.status === 'unknown') {
        const button = element('button', 'ghost is-destructive', '确认该外部动作失败');
        button.type = 'button';
        button.addEventListener('click', () => resolveEffect(effect));
        card.append(button);
      } else {
        card.append(element('p', 'muted', '该状态尚不能人工解析，请等待受 fence 保护的恢复流程。'));
      }
      list.append(card);
    });
  };

  const renderInput = product => {
    const panel = root.querySelector('[data-input-panel]');
    const input = product.control.open_input_requests[0];
    panel.hidden = !input;
    if (!input) return;
    panel.querySelector('[data-input-prompt]').textContent = input.prompt;
    panel.querySelector('[name=objective]').value = product.goal.objective;
    panel.querySelector('[name=constraints]').value = product.goal.success_constraints.join('\n');
  };

  const renderConstraintPolicy = product => {
    const policy = product.constraint_policy;
    root.querySelector('[data-constraint-profile]').textContent = policy.objective_machine_verifiable
      ? '目标使用服务器拥有的“当前证据支撑回答”策略：要求 current EvidenceUse、citation 与有效 provisional artifact。'
      : policy.profile_id
        ? '任务含额外自由文本成功约束，已进入严格语义模式；未注册约束不能由调用方或 Provider 自授 satisfied。'
        : '目标没有匹配的服务器确定性 evaluator，不能由调用方或 Provider 自授 satisfied。';
    const list = root.querySelector('[data-constraint-support]');
    list.replaceChildren();
    if (!policy.semantic_constraints.length) {
      list.append(element('li', '', '没有额外自由文本成功约束。'));
      return;
    }
    policy.semantic_constraints.forEach(constraint => {
      list.append(element(
        'li', '',
        `${constraint.machine_verifiable ? '可机械验证' : '需要改写或服务器注册'} · ${constraint.text}`,
      ));
    });
  };

  const renderTask = product => {
    current = product;
    root.querySelector('[data-task-objective]').textContent = product.goal.objective;
    root.querySelector('[data-task-id]').textContent = `${product.task.task_id} · Goal revision ${product.goal.revision}`;
    root.querySelector('[data-task-status]').textContent = product.task.status_label;
    root.querySelector('[data-task-phase]').textContent = product.state.phase || 'pending';
    root.querySelector('[data-answer-status]').textContent = product.user_completion.label;
    root.querySelector('[data-termination-reason]').textContent = product.state.termination_label;
    root.querySelector('[data-failure-class]').textContent = product.state.failure_class;
    root.querySelector('[data-task-reason]').textContent = product.user_completion.detail;
    root.querySelector('[data-summary-doing]').textContent = product.plain_summary.doing;
    root.querySelector('[data-summary-found]').textContent = product.plain_summary.found;
    root.querySelector('[data-summary-why]').textContent = product.plain_summary.why_stopped;
    root.querySelector('[data-summary-next]').textContent = product.plain_summary.next_action;
    renderConstraintPolicy(product);
    renderControls(product);
    renderEffects(product);
    renderInput(product);
    renderAnswer(product);
    renderEvidence(product);
    renderDeltas(product);
    renderTrace(product);
    loadKnowledge();
    loadPersonalWorkspace();
    showTaskState('content');
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    // A background run can still be claiming a freshly created READY task when
    // the first projection arrives. Keep observing both transitory states so
    // the page reaches the next durable boundary without a manual refresh.
    if (['ready', 'running'].includes(product.task.status)) {
      pollTimer = window.setTimeout(loadTask, 1800);
    }
  };

  async function loadTask() {
    if (!activeTaskId) return;
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    showTaskState('loading');
    try {
      const data = await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}`);
      renderTask(data.product);
      loadList();
    } catch (error) {
      taskError.textContent = error.message;
      showTaskState('error');
    }
  }

  createForm.addEventListener('submit', async event => {
    event.preventDefault();
    const objective = createForm.elements.objective.value.trim();
    const status = root.querySelector('[data-create-status]');
    if (!objective) { status.textContent = '请填写研究目标。'; return; }
    status.textContent = '正在创建研究记录并安全授权模型研究…';
    root.querySelector('[data-create-submit]').disabled = true;
    try {
      const data = await requestJson('/api/research/product/tasks', {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('create'), objective,
          success_constraints: lines(createForm.elements.constraints.value),
          constraint_profile: createForm.elements.constraint_profile.value,
          run_immediately: true,
        }),
      });
      status.textContent = '研究记录已保存；模型正在搜索与取证。';
      createForm.reset();
      setActiveTask(data.outcome.task_id);
    } catch (error) { status.textContent = error.message; }
    finally { root.querySelector('[data-create-submit]').disabled = false; }
  });

  root.querySelector('[data-input-form]').addEventListener('submit', async event => {
    event.preventDefault();
    const input = current.control.open_input_requests[0];
    if (!input) return;
    const context = current.control.action_context;
    const form = event.currentTarget;
    try {
      await requestJson(`/api/research/tasks/${encodeURIComponent(activeTaskId)}/inputs/decisions`, {
        method: 'POST',
        body: JSON.stringify({
          command_id: commandId('input'), input_request_id: input.input_request_id,
          expected_state_version: context.expected_state_version,
          expected_control_generation: context.expected_control_generation,
          decision_kind: 'clarify_goal',
          response: {
            objective: form.elements.objective.value.trim(),
            success_constraints: lines(form.elements.constraints.value),
            evidence_policy: {authority: 'live_current_exact_replay'},
          },
        }),
      });
      await loadTask();
    } catch (error) { root.querySelector('[data-control-status]').textContent = error.message; }
  });

  root.querySelector('[data-refresh-list]').addEventListener('click', loadList);
  root.querySelector('[data-knowledge-intake]').addEventListener('click', () => {
    knowledgeAction('/intake', {command_id: commandId('knowledge-intake')}, '正在接收 immutable KnowledgeDelta snapshot…');
  });
  root.querySelector('[data-knowledge-revalidate]').addEventListener('click', () => {
    knowledgeAction('/revalidate', {command_id: commandId('knowledge-revalidate'), fact_revision_ids: [], trigger: 'explicit'}, '正在追加 current Evidence observations…');
  });
  root.querySelector('[data-artifact-route-form]').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = root.querySelector('[data-knowledge-status]');
    status.textContent = '正在执行 bounded Artifact retrieval、独立 open corpus lane 与 authority gates…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/knowledge/routes/assess`, {
        method: 'POST', body: JSON.stringify({
          command_id: commandId('artifact-route-assess'), query: form.elements.route_query.value.trim(),
          required_aspects: lines(form.elements.route_aspects.value), temporal_scope: {}, viewpoint_scope: {},
          max_artifact_candidates: 5, max_open_results: 5,
        }),
      });
      status.textContent = 'Route assessment已持久保存；ranking不授予reuse authority。';
      await loadKnowledge();
    } catch (error) { status.textContent = error.message; }
  });
  root.querySelector('[data-workspace-record-form]').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const status = root.querySelector('[data-workspace-status]');
    let sourceRefs = [];
    try { sourceRefs = form.elements.source_refs.value.trim() ? JSON.parse(form.elements.source_refs.value) : []; }
    catch (_error) { status.textContent = 'Source refs 必须是 JSON array。'; return; }
    const kind = form.elements.record_kind.value;
    const semanticKey = form.elements.semantic_key.value.trim();
    const value = form.elements.record_value.value.trim();
    const confidenceValue = form.elements.confidence.value;
    const expiresValue = form.elements.expires_at.value;
    status.textContent = '正在创建 typed append-only WorkspaceRecord…';
    try {
      await requestJson(`/api/research/product/tasks/${encodeURIComponent(activeTaskId)}/workspace/records`, {
        method: 'POST', body: JSON.stringify({
          command_id: commandId('workspace-create'), record_kind: kind,
          semantic_key: semanticKey, payload: workspacePayload(kind, semanticKey, value, sourceRefs),
          source_refs: sourceRefs, reason: 'local operator explicit create',
          ...(confidenceValue ? {confidence: Number(confidenceValue)} : {}),
          ...(expiresValue ? {expires_at: new Date(expiresValue).toISOString()} : {}),
        }),
      });
      status.textContent = 'Record 已创建；authority 与 product non-interference 已显式标记。';
      form.reset(); await loadPersonalWorkspace();
    } catch (error) { status.textContent = error.message; }
  });
  root.querySelector('[data-workspace-kind-filter]').addEventListener('change', loadPersonalWorkspace);
  root.querySelector('[data-workspace-status-filter]').addEventListener('change', loadPersonalWorkspace);
  root.querySelector('[data-routing-refresh]').addEventListener('click', loadPersonalWorkspace);
  root.querySelector('[data-assistance-refresh]').addEventListener('click', loadPersonalWorkspace);
  root.querySelector('[data-assistance-enabled]').addEventListener('change', event => {
    assistanceEnabled = event.currentTarget.checked;
    if (assistanceEnabled) {
      journeyEnabled = true;
      root.querySelector('[data-journey-enabled]').checked = true;
    }
    loadPersonalWorkspace();
  });
  root.querySelectorAll('[data-assistance-baseline-snapshot], [data-assistance-current-snapshot]').forEach(control => {
    control.addEventListener('change', loadPersonalWorkspace);
  });
  root.querySelector('[data-routing-enabled]').addEventListener('change', event => {
    routingEnabled = event.currentTarget.checked;
    if (routingEnabled) {
      journeyEnabled = true;
      root.querySelector('[data-journey-enabled]').checked = true;
    }
    loadPersonalWorkspace();
  });
  root.querySelectorAll('[data-routing-explicit-path], [data-routing-provider-permission], [data-routing-cost-permission], [data-routing-asr-permission], [data-routing-video-id]').forEach(control => {
    control.addEventListener('change', loadPersonalWorkspace);
  });
  root.querySelector('[data-personalization-enabled]').addEventListener('change', event => {
    personalizationEnabled = event.currentTarget.checked;
    if (personalizationEnabled) {
      journeyEnabled = true;
      root.querySelector('[data-journey-enabled]').checked = true;
    }
    loadPersonalWorkspace();
  });
  root.querySelector('[data-journey-enabled]').addEventListener('change', event => {
    journeyEnabled = event.currentTarget.checked;
    personalizationEnabled = journeyEnabled;
    routingEnabled = journeyEnabled;
    assistanceEnabled = journeyEnabled;
    root.querySelector('[data-personalization-enabled]').checked = journeyEnabled;
    root.querySelector('[data-routing-enabled]').checked = journeyEnabled;
    root.querySelector('[data-assistance-enabled]').checked = journeyEnabled;
    loadPersonalWorkspace();
  });
  root.querySelector('[data-journey-workspace-focus]').addEventListener('click', () => {
    root.querySelector('[data-personal-workspace]')?.scrollIntoView({behavior: 'smooth'});
  });
  window.addEventListener('popstate', () => {
    const match = location.pathname.match(/^\/research\/([^/]+)$/);
    activeTaskId = match ? decodeURIComponent(match[1]) : '';
    if (activeTaskId) loadTask();
  });

  loadList();
  if (activeTaskId) {
    workspace.hidden = false;
    emptyWorkspace.hidden = true;
    loadTask();
  }
})();

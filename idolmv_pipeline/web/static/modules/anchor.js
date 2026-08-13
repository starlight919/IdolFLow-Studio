// Anchor Generator Module
// ==========================================================================
//
// Handles anchor task CRUD, run management, review/voting, and
// the inline anchor form inside the video-task workflow.

import store from './state.js';
import { api, post } from './api.js';
import { $, $$, toast, escapeHtml, escapeAttr, delay, renderEmptyState, stageName } from './utils.js';

// ── Extracted helpers ──────────────────────────────────────────────────────

function selectedAspectKeys() {
  return [...$$('.aspect-card')]
    .filter((card) => card.querySelector('input[type=checkbox]').checked)
    .map((card) => card.dataset.aspect);
}

function anchorReferencePreview(ref) {
  // Local preview (newly uploaded, not yet saved)
  if (ref._preview) return ref._preview;
  const dataDir = $('#anchor-id').value.trim();
  const path = ref.file.startsWith('anchor-references/') && dataDir
    ? `${dataDir}/anchors/${ref.file}`
    : ref.file;
  return `/api/file-preview?root=data_root&path=${encodeURIComponent(path)}`;
}

function renderReferenceBinding(reference, index, key) {
  const binding = (reference.bindings || []).find((item) => item.aspect === key);
  const label = store.anchorPresets[key]?.label || key;
  if (!binding) {
    return `<section class="reference-binding"><label class="binding-toggle"><input type="checkbox" onchange="renderReferenceBinding"><strong>${escapeHtml(label)}</strong></label></section>`;
  }
  return `<section class="reference-binding active">
    <label class="binding-toggle"><input type="checkbox" checked><strong>${escapeHtml(label)}</strong></label>
    <div class="binding-fields">
      <input value="${escapeHtml(binding.content || '')}" placeholder="参考内容：例如脸型、眼睛、鼻子">
      <input value="${escapeHtml(binding.constraint || '')}" placeholder="约束：例如严格保持身份，不参考妆容">
    </div>
  </section>`;
}

// ── Anchor Task Form ────────────────────────────────────────────────────────

function anchorTaskForm() {
  const aspects = [...$$('.aspect-card')]
    .filter((card) => card.querySelector('input[type=checkbox]').checked)
    .map((card) => {
      const key = card.dataset.aspect;
      const preset = card.querySelector('.aspect-preset').value;
      const extra = card.querySelector('.aspect-extra').value.trim();
      const text = preset ? store.anchorPresets[key].presets[preset] : '';
      return {
        key,
        description: [text, extra].filter(Boolean).join(' '),
        priority: card.querySelector('.aspect-priority').value,
      };
    });

  // Build reference bindings from per-aspect source dropdowns
  // aspect → reference-slot index
  const refBindings = {};   // refIdx → [{aspect, content, constraint}]
  $$('.aspect-card').forEach((card) => {
    const checkbox = card.querySelector('input[type=checkbox]');
    if (!checkbox || !checkbox.checked) return;
    const srcSel = card.querySelector('.aspect-source');
    const refIdx = srcSel ? srcSel.value : '';
    if (refIdx === '' || refIdx === null) return;
    const key = card.dataset.aspect;
    const extraInput = card.querySelector('.aspect-extra');
    if (!refBindings[refIdx]) refBindings[refIdx] = [];
    refBindings[refIdx].push({
      aspect: key,
      content: extraInput ? extraInput.value.trim() : '',
      constraint: '',
    });
  });

  const description = buildPresetText('#anchor-description', 'quality');
  const negative = buildPresetText('#anchor-negative', 'negative');

  return {
    id: $('#anchor-id').value.trim(),
    name: $('#anchor-name').value.trim(),
    data_dir: $('#anchor-id').value.trim(),
    model: 'gpt-image-2',
    candidates: Number($('#anchor-candidates').value),
    size: $('#anchor-size').value,
    resolution: $('#anchor-resolution').value,
    description,
    negative,
    aspects,
    references: store.anchorReferences.map((r, i) => ({
      id: r.id || `ref-${i + 1}`,
      file: r.file,
      bindings: refBindings[String(i)] || [],
      note: r.note || '',
      remove_watermark: !!r.remove_watermark,
    })),
  };
}

// ── Rendering ───────────────────────────────────────────────────────────────

export function renderAnchorAspects() {
  const defaults = {
    identity_face: 'same_person',
    hair_texture: 'real_hair',
    skin_texture: 'real_skin',
    composition_camera: 'half_body',
    visual_style: 'photoreal',
  };

  // Save current source selections before re-render
  const savedSources = {};
  $$('.aspect-source').forEach((sel) => {
    savedSources[sel.dataset.aspect] = sel.value;
  });

  const container = $('#anchor-aspects');
  if (!container) return;
  container.innerHTML = Object.entries(store.anchorPresets)
    .map(([key, item]) => {
      const defaultVal = defaults[key] || '';
      return `<article class="aspect-card" data-aspect="${key}">
        <label class="aspect-title">
          <input type="checkbox" ${defaults[key] ? 'checked' : ''}>
          <strong>${escapeHtml(item.label)}</strong>
        </label>
        <div class="aspect-row">
          <select class="aspect-source" data-aspect="${key}" onchange="onAspectSourceChange()">
            <option value="">不需参考图</option>
          </select>
          <select class="aspect-preset">
            <option value="">不使用预设</option>
            ${Object.entries(item.presets).map(([id, text]) => `<option value="${id}" ${defaultVal === id ? 'selected' : ''}>${escapeHtml(text)}</option>`).join('')}
          </select>
        </div>
        <div class="aspect-row">
          <input class="aspect-extra" placeholder="可选补充要求">
          <select class="aspect-priority">
            <option value="required">必须满足</option>
            <option value="locked">严格保持</option>
            <option value="preferred">优先参考</option>
          </select>
        </div>
      </article>`;
    })
    .join('');

  syncAspectSourceDropdowns(savedSources);
}

export function renderAnchorReferences() {
  const list = $('#anchor-reference-list');
  if (!list) return;

  if (!store.anchorReferences.length) {
    list.innerHTML = '<p class="hint">尚未添加参考图片。上传后点击图片可展开选择参考点。</p>';
    renderAspectSourceSummary();
    return;
  }

  // Read current aspect-source bindings (from step 4 dropdowns — these
  // are already synced by toggleRefAspectBinding / onAspectSourceChange)
  const imageAspects = {};
  $$('.aspect-source').forEach((sel) => {
    const refIdx = sel.value;
    if (refIdx === '' || refIdx === null) return;
    const key = sel.dataset.aspect;
    if (!imageAspects[refIdx]) imageAspects[refIdx] = [];
    imageAspects[refIdx].push(key);
  });

  const presets = Object.entries(store.anchorPresets);

  list.innerHTML = store.anchorReferences
    .map((r, i) => {
      const boundAspects = imageAspects[String(i)] || [];
      const labels = boundAspects.map((k) => store.anchorPresets[k]?.label || k);
      const hasBindings = boundAspects.length > 0;
      return `<article class="reference-card" id="ref-card-${i}">
        <div class="ref-thumb-wrap" onclick="toggleRefExpand(${i})">
          <img class="reference-thumb" src="${anchorReferencePreview(r)}" loading="lazy">
          <span class="ref-expand-icon">${hasBindings ? '▾' : '▸'}</span>
        </div>
        <div class="reference-summary">
          <strong onclick="toggleRefExpand(${i})" style="cursor:pointer">图${i + 1}: ${escapeHtml(r.file.split('/').pop())}</strong>
          ${hasBindings
            ? `<span class="ref-aspect-tags">${labels.map((l) => `<span class="ref-aspect-tag">${escapeHtml(l)}</span>`).join(' ')}</span>`
            : '<span class="ref-aspect-tags muted">点击展开选择参考点</span>'}
          <label class="watermark-option">
            <input type="checkbox" ${r.remove_watermark ? 'checked' : ''} onchange="toggleAnchorWatermark(${i}, this.checked)">
            <span>去除水印/文字</span>
          </label>
          <button type="button" class="secondary" onclick="removeAnchorReference(${i})">移除</button>
        </div>
        <div class="ref-expandable" id="ref-expand-${i}" ${hasBindings ? '' : 'hidden'}>
          <div class="ref-aspect-checks">
            ${presets.map(([key, item]) => {
              const isBound = boundAspects.includes(key);
              return `<label class="ref-aspect-check">
                <input type="checkbox"
                  data-ref="${i}" data-aspect="${key}"
                  ${isBound ? 'checked' : ''}
                  onchange="toggleRefAspectBinding(${i}, '${key}', this.checked)">
                <span>${escapeHtml(item.label)}</span>
              </label>`;
            }).join('')}
          </div>
          <input value="${escapeHtml(r.note || '')}" class="ref-note" placeholder="补充描述（可选）"
            onchange="store.anchorReferences[${i}].note = this.value">
        </div>
      </article>`;
    })
    .join('');

  renderAspectSourceSummary();
}

/** Toggle expand/collapse of a reference card's aspect binding section */
function toggleRefExpand(refIndex) {
  const el = document.getElementById(`ref-expand-${refIndex}`);
  if (!el) return;
  el.hidden = !el.hidden;
  // Update the expand icon
  const icon = document.querySelector(`#ref-card-${refIndex} .ref-expand-icon`);
  if (icon) icon.textContent = el.hidden ? '▸' : '▾';
}
window.toggleRefExpand = toggleRefExpand;

/** Bind/unbind an aspect to a reference image from the expanded card */
export function toggleRefAspectBinding(refIndex, aspectKey, checked) {
  // Update the corresponding aspect-source dropdown in step 4
  const sel = document.querySelector(`.aspect-source[data-aspect="${aspectKey}"]`);
  if (sel) {
    sel.value = checked ? String(refIndex) : '';
  }
  // Auto-check the corresponding aspect card checkbox in step 4
  const card = document.querySelector(`.aspect-card[data-aspect="${aspectKey}"]`);
  if (card) {
    const checkbox = card.querySelector('input[type=checkbox]');
    if (checkbox) checkbox.checked = checked;
  }
  // Re-render both views to stay in sync
  renderAnchorReferences();
  renderAspectSourceSummary();
}

// ── Anchor Form Actions ─────────────────────────────────────────────────────

export async function prepareAnchors() {
  if (!Object.keys(store.anchorPresets).length) {
    const data = await api('/api/anchor-presets');
    store.anchorPresets = data.aspects || data;  // backward compat
    store.qualityPresets = data.quality || {};
    store.negativePresets = data.negative || {};
    renderAnchorAspects();
    renderAnchorQualityPresets();
    renderAnchorNegativePresets();
  }
  await Promise.all([loadAnchorTasks(), loadAnchorRuns()]);
}

export async function saveAnchorTask(event) {
  event?.preventDefault();

  // The anchor-id field IS the data directory name — it must be filled in.
  const taskId = $('#anchor-id').value.trim();
  if (!taskId) return toast('请先选择数据目录');
  const pending = store.anchorReferences.filter((r) => r._blob);
  if (pending.length) {
    for (const ref of pending) {
      try {
        const uploaded = await uploadFile(ref._blob, ref.file, 'anchor-references', taskId);
        // Upload returns path relative to data dir (e.g. "anchors/anchor-references/x.jpg").
        // AnchorTaskStore expects path relative to the anchors/ subdir.
        ref.file = uploaded.file.replace(/^anchors\//, '');
        delete ref._blob;
        delete ref._preview;
      } catch (e) {
        toast(`上传 ${ref.file} 失败: ${e.message}`);
        return;
      }
    }
  }

  const task = await post('/api/anchor-tasks', anchorTaskForm());
  $('#anchor-id').value = task.id;
  toast('Anchor 任务已保存');
  await loadAnchorTasks();
  // Scroll to the task list so user can see where it went
  const taskList = $('#anchor-task-list');
  if (taskList) setTimeout(() => scrollTo({ top: taskList.offsetTop - 40, behavior: 'smooth' }), 200);
  return task;
}

function uploadFile(blob, filename, category, taskId) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/uploads');
    xhr.setRequestHeader('X-Task-Id', taskId);
    xhr.setRequestHeader('X-Filename', encodeURIComponent(filename));
    xhr.setRequestHeader('X-Category', category);
    xhr.onload = () => {
      if (xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else reject(new Error(JSON.parse(xhr.responseText).error || 'Upload failed'));
    };
    xhr.onerror = () => reject(new Error('网络错误'));
    xhr.send(blob);
  });
}

export function resetAnchorForm() {
  $('#anchor-form').reset();
  store.anchorReferences = [];
  renderAnchorAspects();
  renderAnchorReferences();
}

export async function previewAnchorPrompt() {
  try {
    const result = await post('/api/anchor-prompt-preview', anchorTaskForm());
    const el = $('#anchor-prompt-preview');
    if (el) {
      el.hidden = false;
      el.textContent = result.prompt;
    }
  } catch (e) {
    toast(e.message);
  }
}

export async function requestAnchorStart() {
  try {
    const task = await saveAnchorTask();
    store.pendingAnchorTask = task.id;
    store.pendingTask = null;
    $('#submit-password').value = '';
    $('#modal').hidden = false;
    $('#submit-password').focus();
  } catch (e) {
    toast(e.message);
  }
}

export function uploadAnchorReference() {
  const file = $('#anchor-upload-file').files[0];
  if (!file) return toast('请先选择一张图片');

  // Validate image type
  if (!file.type.startsWith('image/')) return toast('仅支持图片文件');

  const reader = new FileReader();
  reader.onload = () => {
    store.anchorReferences.push({
      id: `ref-${store.anchorReferences.length + 1}`,
      file: file.name,
      bindings: [],  // No auto-binding — user selects source per aspect in step 3
      note: '',
      remove_watermark: false,
      // Store raw data for deferred upload at save time
      _blob: file,
      _preview: reader.result,
    });
    renderAnchorReferences();
    syncAspectSourceDropdowns();
    toast(`已添加参考图: ${file.name} → 请到 step 3 为参考点指定来源`);
  };
  reader.onerror = () => toast('读取图片失败，请重试');
  reader.readAsDataURL(file);
}

/**
 * Remove a reference image by index.
 */
export function removeAnchorReference(index) {
  store.anchorReferences.splice(index, 1);
  syncAspectSourceDropdowns();
  renderAnchorReferences();
}

/**
 * Callback for watermark toggle from reference card.
 */
export function toggleAnchorWatermark(index, checked) {
  if (store.anchorReferences[index]) {
    store.anchorReferences[index].remove_watermark = checked;
  }
}

/**
 * Sync all .aspect-source dropdowns to match current reference list.
 * @param {Object<string,string>|null} preselected  optional {aspectKey: refIdx} to restore
 */
export function syncAspectSourceDropdowns(preselected) {
  const refs = store.anchorReferences;
  $$('.aspect-source').forEach((sel) => {
    const key = sel.dataset.aspect;
    const current = preselected ? (preselected[key] !== undefined ? preselected[key] : sel.value) : sel.value;
    sel.innerHTML = '<option value="">不需参考图</option>' +
      refs.map((r, i) => {
        const label = r.file.split('/').pop();
        return `<option value="${i}" ${current === String(i) ? 'selected' : ''}>图${i + 1} - ${escapeHtml(label)}</option>`;
      }).join('');
  });
}

/**
 * Called when any aspect-source dropdown changes — refreshes reference summary.
 */
export function onAspectSourceChange() {
  // Auto-check aspect card when a reference source is selected
  $$('.aspect-source').forEach((sel) => {
    const card = document.querySelector(`.aspect-card[data-aspect="${sel.dataset.aspect}"]`);
    if (!card) return;
    const checkbox = card.querySelector('input[type=checkbox]');
    if (!checkbox) return;
    if (sel.value !== '' && sel.value !== null) {
      checkbox.checked = true;
    }
  });

  // Preserve which reference cards are currently expanded
  const expanded = new Set();
  store.anchorReferences.forEach((_, i) => {
    const el = document.getElementById(`ref-expand-${i}`);
    if (el && !el.hidden) expanded.add(i);
  });
  renderAnchorReferences();
  // Restore expand states
  expanded.forEach((i) => {
    const el = document.getElementById(`ref-expand-${i}`);
    if (el) el.hidden = false;
    const icon = document.querySelector(`#ref-card-${i} .ref-expand-icon`);
    if (icon) icon.textContent = '▾';
  });
  renderAspectSourceSummary();
}

/**
 * Show a summary bar above aspects showing which image each aspect maps to.
 */
export function renderAspectSourceSummary() {
  const bar = $('#aspect-source-summary');
  if (!bar) return;

  const map = {};
  $$('.aspect-source').forEach((sel) => {
    const refIdx = sel.value;
    if (refIdx === '' || refIdx === null) return;
    const key = sel.dataset.aspect;
    const card = document.querySelector(`.aspect-card[data-aspect="${key}"]`);
    if (!card || card.querySelector('input[type=checkbox]')?.checked === false) return;
    if (!map[refIdx]) map[refIdx] = [];
    map[refIdx].push(key);
  });

  if (!Object.keys(map).length) {
    bar.hidden = true;
    return;
  }

  bar.hidden = false;
  bar.innerHTML = '<strong>当前映射</strong>：' +
    Object.entries(map).map(([idx, keys]) => {
      const labels = keys.map((k) => `<span class="map-tag">${escapeHtml(store.anchorPresets[k]?.label || k)}</span>`).join(' ');
      return `<span class="map-group">图${Number(idx) + 1} → ${labels}</span>`;
    }).join(' &nbsp;|&nbsp; ');
}

// ── Anchor Task List ────────────────────────────────────────────────────────

export async function loadAnchorTasks() {
  store.anchorTasks = await api('/api/anchor-tasks');
  let orphaned = [];
  try {
    orphaned = await api('/api/anchor-tasks/orphaned');
  } catch (_) { /* ignore orphan fetch errors */ }
  store.orphanedAnchorTasks = orphaned;
  const list = $('#anchor-task-list');
  if (!list) return;

  // Merge orphaned tasks into the regular list — each orphan is shown as a
  // disabled card with a single "恢复" action, same layout as normal tasks.
  const orphanCards = orphaned.map((o) => ({
    id: o.task_id,
    name: o.task_name,
    _orphan: true,
    _refCount: o.reference_count,
    _refFiles: o.reference_files,
  }));

  const all = [...store.anchorTasks.map((t) => ({ ...t, _orphan: false })), ...orphanCards];

  const html = all
    .map(
      (t) => {
        if (t._orphan) {
          return `<article class="task" data-id="${escapeHtml(t.id)}">
            <div>
              <h3>${escapeHtml(t.name)}</h3>
              <div class="meta">配置已丢失 · ${t._refCount} 张参考图 · ${t._refFiles.map((f) => escapeHtml(f)).join(', ')}</div>
            </div>
            <div class="actions">
              <button class="secondary" onclick="recoverAnchorTask('${escapeAttr(t.id)}')">恢复</button>
            </div>
          </article>`;
        }
        return `<article class="task" data-id="${escapeHtml(t.id)}">
          <div><h3>${escapeHtml(t.name)}</h3><div class="meta">📁 ${escapeHtml(t.data_dir || t.id)} · GPT Image 2 · ${t.references.length} 张参考图 · ${t.candidates} 候选</div></div>
          <div class="actions">
            <button class="secondary" data-action="anchor-edit">编辑</button>
            <button data-action="anchor-start">生成</button>
            <button class="danger" data-action="anchor-delete" onclick="event.stopPropagation(); confirmDeleteAnchorTask('${escapeAttr(t.id)}')">删除</button>
          </div>
        </article>`;
      }
    )
    .join('');
  list.innerHTML = html || renderEmptyState('🧩', '还没有 Anchor 任务', '使用表单生成候选图片后可设为 Anchor');
}

export async function recoverAnchorTask(taskId) {
  if (!confirm(`将尝试从残余数据恢复 Anchor 任务「${taskId}」，恢复后需重新配置参考点绑定。`)) return;
  try {
    const task = await post(`/api/anchor-tasks/${encodeURIComponent(taskId)}/recover`);
    toast(`已恢复: ${task.id}`);
    await loadAnchorTasks();
  } catch (e) {
    toast(`恢复失败: ${e.message}`);
  }
}

export function editAnchorTask(id) {
  const t = store.anchorTasks.find((x) => x.id === id);
  if (!t) return;
  $('#anchor-name').value = t.name;
  $('#anchor-id').value = t.id;
  $('#anchor-candidates').value = t.candidates;
  $('#anchor-size').value = t.size;
  $('#anchor-resolution').value = t.resolution;
  $('#anchor-description').value = t.description || '';
  $('#anchor-negative').value = t.negative || '';
  // Restore quality/negative preset tag selections
  setTimeout(() => restorePresetSelections(t.description || '', t.negative || ''), 50);

  // First set references so renderAnchorAspects() can populate dropdowns
  store.anchorReferences = t.references.map((x) => ({
    ...x,
    bindings: (x.bindings || (x.aspects || []).map((a) => ({ aspect: a, content: '', constraint: '' }))).map((b) => ({ ...b })),
  }));

  // Build ref→aspect mapping from the saved bindings
  const savedSources = {};
  store.anchorReferences.forEach((ref, refIdx) => {
    (ref.bindings || []).forEach((b) => {
      savedSources[b.aspect] = refIdx;
    });
  });

  // Re-render aspect cards so dropdowns contain reference options (图1, 图2…)
  renderAnchorAspects(savedSources);

  // Restore aspect checkboxes and extras from task data
  $$('.aspect-card').forEach((card) => {
    const a = t.aspects.find((x) => x.key === card.dataset.aspect);
    card.querySelector('input[type=checkbox]').checked = !!a;
    card.querySelector('.aspect-extra').value = a?.description || '';
    card.querySelector('.aspect-preset').value = '';
    if (a) card.querySelector('.aspect-priority').value = a.priority;
  });

  // Set source dropdowns from reference bindings
  store.anchorReferences.forEach((ref, refIdx) => {
    (ref.bindings || []).forEach((b) => {
      const card = document.querySelector(`.aspect-card[data-aspect="${b.aspect}"]`);
      if (!card) return;
      const srcSel = card.querySelector('.aspect-source');
      if (srcSel) srcSel.value = String(refIdx);
    });
  });

  // Now render references with correct bindings visible
  renderAnchorReferences();

  scrollTo({ top: 0, behavior: 'smooth' });
}

export async function deleteAnchorTask(id) {
  // 确认弹窗已由事件委托 / confirmDeleteAnchorTask 统一处理
  try {
    const resp = await fetch(`/api/anchor-tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(body.error || '删除失败');
    }
    toast(`已删除: ${id}`);
    await loadAnchorTasks();
  } catch (e) { toast(`删除失败: ${e.message}`); }
}

// ── Anchor Runs ─────────────────────────────────────────────────────────────

export async function loadAnchorRuns() {
  store.anchorRuns = await api('/api/anchor-runs');

  // ── Render progress cards (all runs including queued/running) ──
  const list = $('#anchor-run-list');
  if (list) {
    list.innerHTML = store.anchorRuns.length
      ? store.anchorRuns.map(anchorRunCard).join('')
      : renderEmptyState('🖼️', '还没有 Anchor 运行记录', '提交 Anchor 任务后将在此显示进度');
  }

  // ── Populate review dropdown (only completed runs with manifests) ──
  const select = $('#anchor-review-run');
  if (!select) return;
  const current = select.value;
  const completed = store.anchorRuns.filter((r) => r.manifest);
  select.innerHTML = completed
    .map((r) => `<option value="${r.run_id}">${escapeHtml(r.task_name)} · ${r.run_id}</option>`)
    .join('');
  if (completed.some((r) => r.run_id === current)) select.value = current;
  if (select.value) loadAnchorReview(select.value);
}

function anchorRunCard(r) {
  const percent = r.total ? Math.round(((r.completed || 0) / r.total) * 100) : r.status === 'completed' ? 100 : 0;
  const isRunning = ['queued', 'running'].includes(r.status);
  const canReview = r.manifest || r.status === 'running';
  const resumeBtn = r.can_resume ? `<button class="run-resume" onclick="event.stopPropagation(); resumeAnchorRun('${escapeAttr(r.run_id)}')" title="重新恢复轮询">↻ 恢复</button>` : '';
  return `<article class="run-card${canReview ? ' clickable' : ''}" data-id="${escapeHtml(r.run_id)}"${canReview ? ` onclick="openAnchorRunReview('${escapeAttr(r.run_id)}')"` : ''}>
    <div class="run-main">
      <h3>${escapeHtml(r.task_name)} <span class="badge">${stageName(r.stage)}</span></h3>
      <div class="meta">${r.run_id} · ${escapeHtml(r.message || '')}</div>
      <div class="progress"><i style="width:${percent}%"></i></div>
    </div>
    <div class="run-right">
      <strong>${r.completed || 0}/${r.total || 0}</strong>
      ${r.error ? `<div class="meta">${escapeHtml(r.error)}</div>` : ''}
      ${resumeBtn}
    </div>
    <button class="run-delete" data-action="run-delete" onclick="event.stopPropagation(); confirmDeleteRun('${escapeAttr(r.run_id)}', this)" title="${isRunning ? '运行中无法删除' : '删除此记录'}" ${isRunning ? 'disabled' : ''}>✕</button>
  </article>`;
}

export function openAnchorPoll() {
  clearInterval(store.anchorPollTimer);
  store.anchorPollTimer = setInterval(async () => {
    if (!$('#anchors').classList.contains('active')) return;
    await loadAnchorRuns();
    if (!store.anchorRuns.some((r) => ['queued', 'running'].includes(r.status)))
      clearInterval(store.anchorPollTimer);
  }, 1500);
}

// ── Anchor Review ───────────────────────────────────────────────────────────

export async function loadAnchorReview(runId) {
  if (!runId) return;
  store.anchorManifest = await api(`/api/anchor-runs/${runId}/manifest`);
  store.anchorReviewState = store.anchorManifest.review_state || { votes: {}, published: {} };
  renderAnchorReview();
}

function renderAnchorReview() {
  const run = $('#anchor-review-run').value;
  if (!store.anchorManifest) return;
  const selected = store.anchorManifest.candidates.filter(
    (c) => store.anchorReviewState.votes[c.id] === 'up' && !store.anchorReviewState.published[c.id]
  );

  const toolbar = $('#anchor-review-toolbar');
  if (toolbar) {
    toolbar.innerHTML = `<button class="secondary" data-action="anchor-regenerate">按当前配置再生成一批</button>
      <button data-action="anchor-promote-selected">批量设为 Anchor (${selected.length})</button>`;
  }

  const content = $('#anchor-review-content');
  if (!content) return;
  content.innerHTML = store.anchorManifest.candidates
    .map((c) => {
      const vote = store.anchorReviewState.votes[c.id];
      const used = store.anchorReviewState.published[c.id];
      return `<article class="anchor-review-card ${used ? 'published' : ''}" data-id="${c.id}">
        <img src="/api/anchor-runs/${run}/media/${encodeURIComponent(c.id)}">
        <div class="review-meta">
          <strong>候选 ${String(c.candidate).padStart(2, '0')}</strong>
          <span>${store.anchorManifest.size}</span>
        </div>
        <div class="review-actions">
          <button class="${vote === 'up' ? 'selected' : ''}" data-action="anchor-vote" data-vote="up">推荐</button>
          <button class="${vote === 'down' ? 'selected' : ''}" data-action="anchor-vote" data-vote="down">不推荐</button>
          <a href="/api/anchor-runs/${run}/download/${encodeURIComponent(c.id)}">下载</a>
          <button data-action="anchor-promote" ${used ? 'disabled' : ''}>${used ? '已设为 Anchor' : '设为 Anchor'}</button>
        </div>
      </article>`;
    })
    .join('');
}

export async function regenerateAnchorBatch() {
  store.pendingAnchorTask = store.anchorManifest.task;
  store.pendingTask = null;
  $('#submit-password').value = '';
  $('#modal').hidden = false;
  $('#submit-password').focus();
}

export async function anchorVote(id, vote, button) {
  const run = $('#anchor-review-run').value;
  await post(`/api/anchor-runs/${run}/vote`, { id, vote });
  store.anchorReviewState.votes[id] = vote;
  button.parentElement.querySelectorAll('button').forEach((b) => b.classList.remove('selected'));
  button.classList.add('selected');
}

export async function promoteAnchor(id) {
  try {
    const result = await post(`/api/anchor-runs/${$('#anchor-review-run').value}/promote`, { id });
    store.anchorReviewState.published[id] = result;
    renderAnchorReview();
    toast('已设为 Anchor，图片位于 anchors/selected/');
  } catch (e) {
    toast(e.message);
  }
}

export async function promoteSelectedAnchors() {
  if (!store.anchorManifest) return;
  const selected = store.anchorManifest.candidates.filter(
    (c) => store.anchorReviewState.votes[c.id] === 'up' && !store.anchorReviewState.published[c.id]
  );
  for (const candidate of selected) {
    await promoteAnchor(candidate.id);
  }
}

// ── Folder Picker (reuses the folder modal from task.js) ───────────────────

export function openAnchorFolderPicker() {
  store.folderPath = '';
  store.folderPickerTarget = 'anchor';
  $('#folder-modal').hidden = false;
  // browseFolder is defined in task module and attached to window
  if (window.browseFolder) window.browseFolder('');
}

// ── Pick Anchor References ──────────────────────────────────────────────────

export async function pickAnchorReferences() {
  store.anchorPickerMode = true;
  store.assetPickerCategory = 'anchor-references';
  const dataDir = $('#anchor-id').value.trim();
  // Anchor references live under <dataDir>/anchors/, so navigate there directly.
  store.assetPickerRoot = dataDir ? `${dataDir}/anchors` : '';
  store.assetPickerPath = store.assetPickerRoot;
  store.assetPickerSelected = new Set();
  $('#asset-picker-title').textContent = '选择 Anchor 参考图片';
  $('#asset-picker-modal').hidden = false;
  // browseAssets is defined in task module, called via window
}

export async function openInlineAnchor() {
  showView('anchors');  // defined in app module
  // Pre-fill the anchor data directory from the current video task form
  const taskDir = $('#task-dir')?.value.trim() || '';
  const taskName = $('#task-name')?.value.trim() || '';
  if (taskDir) {
    $('#anchor-id').value = taskDir;
    $('#anchor-name').value = taskName || taskDir;
  }
}

// Set anchor source toggle
export function setAnchorSource(source) {
  $$('[data-anchor-source]').forEach((b) => b.classList.toggle('active', b.dataset.anchorSource === source));
  $('#existing-anchor-source').hidden = source !== 'existing';
  $('#generate-anchor-source').hidden = source !== 'generate';
}

// Helper for auto-fill (used from app.js)
export function autoFillAnchorFields(source) {
  const nameEl = $('#anchor-name');
  const idEl = $('#anchor-id');
  const value = source.value.trim();
  if (!value) return;
  const idFriendly = value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-').replace(/^-+|-+$/g, '');
  if (source === nameEl) {
    if (!idEl.value.trim() || idEl.dataset.autoFilled === 'true') {
      idEl.value = idFriendly;
      idEl.dataset.autoFilled = 'true';
    }
  } else if (source === idEl) {
    if (!nameEl.value.trim() || nameEl.dataset.autoFilled === 'true') {
      nameEl.value = value;
      nameEl.dataset.autoFilled = 'true';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// Prompt Optimizer — Anchor-based Reference Mapping
// ═══════════════════════════════════════════════════════════════════

let _lastOptimizerResult = null;
window._lastOptimizerResult = null;

// Category display metadata
const CATEGORY_META = {
  subject:      { label: '人物主体', icon: '👤', order: 1 },
  appearance:   { label: '穿着配饰', icon: '👔', order: 2 },
  environment:  { label: '场景环境', icon: '🏠', order: 3 },
  objects:      { label: '独立物体', icon: '📦', order: 4 },
  composition:  { label: '构图姿态', icon: '📐', order: 5 },
  photography:  { label: '摄影风格', icon: '📷', order: 6 },
  edit:         { label: '编辑操作', icon: '✏️', order: 7 },
};

const OP_LABELS = {
  preserve: '保持',
  transfer: '迁移',
  match: '匹配',
  remove: '移除',
  replace: '替换',
  add: '添加',
  modify: '修改',
};

const PRIORITY_LABELS = {
  critical: '关键',
  high: '高',
  medium: '中',
  low: '低',
};

export async function runPromptOptimizer() {
  const input = $('#optimizer-input');
  const btn = $('#optimizer-btn');
  const sourceLabel = $('#optimizer-source');
  const output = $('#optimizer-output');
  const schema = $('#optimizer-schema');
  const prompt = $('#optimizer-prompt');
  const applyBtn = $('#optimizer-apply-btn');
  const mappingTable = $('#optimizer-mapping-table');
  const objectsSection = $('#optimizer-objects-section');
  const objectsList = $('#optimizer-objects-list');
  const text = input.value.trim();

  if (!text) return toast('请先输入你的图文合成需求');

  btn.disabled = true;
  btn.textContent = '解析中…';
  sourceLabel.textContent = '';
  output.hidden = true;
  applyBtn.disabled = true;
  _lastOptimizerResult = null;

  try {
    const result = await post('/api/anchor-optimize', { text, references: [] });
    _lastOptimizerResult = result;
    window._lastOptimizerResult = result;

    // ── Build anchor mapping table ──
    const anchors = result.anchors || [];
    // Group by category
    const groups = {};
    for (const a of anchors) {
      const cat = a.category || 'subject';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(a);
    }

    // Render mapping table by category
    let tableHtml = '<table class="anchor-table"><thead><tr><th>类别</th><th>视觉属性</th><th>来源图</th><th>操作</th><th>优先级</th><th>说明</th></tr></thead><tbody>';

    const catOrder = ['subject', 'appearance', 'environment', 'objects', 'composition', 'photography', 'edit'];
    for (const cat of catOrder) {
      const items = groups[cat];
      if (!items || !items.length) continue;
      const meta = CATEGORY_META[cat] || { label: cat, icon: '' };
      const rowSpan = items.length;
      let firstRow = true;
      for (const a of items) {
        const typeLabel = a.type || '';
        const sourceLabel = a.source || '—';
        const opLabel = OP_LABELS[a.operation] || a.operation || '—';
        const priLabel = PRIORITY_LABELS[a.priority] || a.priority || '—';
        const desc = a.description || '';
        const objectHint = a.object_name ? ` [${a.object_name}]` : '';

        tableHtml += '<tr>';
        if (firstRow) {
          tableHtml += `<td rowspan="${rowSpan}" class="cat-cell"><span class="cat-icon">${meta.icon}</span><span class="cat-label">${meta.label}</span></td>`;
          firstRow = false;
        }
        tableHtml += `<td class="anchor-type-cell">${escapeHtml(typeLabel)}${escapeHtml(objectHint)}</td>`;
        tableHtml += `<td class="source-cell"><span class="source-tag">${escapeHtml(sourceLabel)}</span></td>`;
        tableHtml += `<td class="op-cell"><span class="op-tag op-${escapeAttr(a.operation)}">${escapeHtml(opLabel)}</span></td>`;
        tableHtml += `<td class="pri-cell"><span class="pri-tag pri-${escapeAttr(a.priority)}">${escapeHtml(priLabel)}</span></td>`;
        tableHtml += `<td class="desc-cell">${escapeHtml(desc)}</td>`;
        tableHtml += '</tr>';
      }
    }
    tableHtml += '</tbody></table>';
    mappingTable.innerHTML = tableHtml;

    // ── Objects list ──
    const objects = result.objects || [];
    if (objects.length) {
      objectsSection.hidden = false;
      objectsList.innerHTML = objects.map((o) => {
        const preserve = (o.preserve || []).join('、');
        const pos = o.position || 'beside_subject';
        return `<div class="object-item">
          <span class="object-name">📦 ${escapeHtml(o.name)}</span>
          <span class="object-source">← ${escapeHtml(o.source || '—')}</span>
          <span class="object-op">${escapeHtml(OP_LABELS[o.operation] || o.operation)}</span>
          ${preserve ? `<span class="object-preserve">保留: ${escapeHtml(preserve)}</span>` : ''}
          <span class="object-pos">位置: ${escapeHtml(pos)}</span>
        </div>`;
      }).join('');
    } else {
      objectsSection.hidden = true;
    }

    // Schema + prompt
    schema.textContent = JSON.stringify(result.structured_schema, null, 2);
    prompt.textContent = result.canonical_prompt;

    sourceLabel.textContent = result.source === 'gpt' ? '由 GPT 解析' : '由关键词解析';
    output.hidden = false;
    applyBtn.disabled = false;
  } catch (e) {
    toast(`解析失败: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '智能解析';
  }
}

export function applyOptimizerResult() {
  const result = _lastOptimizerResult || window._lastOptimizerResult;
  if (!result) return toast('请先执行智能解析');

  const anchors = result.anchors || [];
  const objects = result.objects || [];
  const composition = result.composition || {};
  const schema = result.structured_schema || {};

  // ── Map anchor types to form aspect keys ──
  const TYPE_TO_ASPECT_KEY = {
    identity: 'identity_face',
    facial_features: 'identity_face',
    face_shape: 'identity_face',
    hairstyle: 'hair_style',
    hair_texture: 'hair_texture',
    skin_texture: 'skin_texture',
    body_shape: 'identity_face',
    body_proportion: 'composition_camera',
    clothing: 'wardrobe',
    shoes: 'wardrobe',
    glasses: 'wardrobe',
    hat: 'wardrobe',
    earrings: 'wardrobe',
    necklace: 'wardrobe',
    bag: 'wardrobe',
    accessories: 'wardrobe',
    scene: 'scene',
    background: 'scene',
    foreground: 'scene',
    furniture: 'scene',
    architecture: 'scene',
    weather: 'scene',
    time_of_day: 'scene',
    scene_objects: 'scene',
    pose: 'pose_expression',
    framing: 'composition_camera',
    camera_angle: 'composition_camera',
    facing_direction: 'composition_camera',
    subject_position: 'composition_camera',
    lighting: 'lighting',
    exposure: 'lighting',
    camera_style: 'visual_style',
    depth_of_field: 'visual_style',
    texture_realism: 'visual_style',
  };

  // Collect which form aspect keys are activated
  const activatedKeys = new Set();
  const keyDescriptions = {};  // key → accumulated descriptions
  const keyPriorities = {};    // key → priority

  for (const a of anchors) {
    if (a.category === 'edit') continue;  // edits go to negative constraints
    if (a.type === 'object') continue;    // objects handled separately
    const formKey = TYPE_TO_ASPECT_KEY[a.type];
    if (!formKey) continue;
    activatedKeys.add(formKey);

    // Accumulate descriptions
    if (a.description) {
      keyDescriptions[formKey] = keyDescriptions[formKey]
        ? keyDescriptions[formKey] + '；' + a.description
        : a.description;
    }

    // Use highest priority
    const priOrder = { critical: 4, high: 3, medium: 2, low: 1 };
    const currentPri = priOrder[keyPriorities[formKey]] || 0;
    const newPri = priOrder[a.priority] || 0;
    if (newPri > currentPri) {
      keyPriorities[formKey] = a.priority;
    }
  }

  // Also include composition settings
  if (composition.pose) {
    activatedKeys.add('pose_expression');
    keyDescriptions['pose_expression'] = keyDescriptions['pose_expression']
      ? keyDescriptions['pose_expression'] + '；' + composition.pose
      : composition.pose;
  }
  if (composition.framing) {
    activatedKeys.add('composition_camera');
    keyDescriptions['composition_camera'] = keyDescriptions['composition_camera']
      ? keyDescriptions['composition_camera'] + '；' + composition.framing
      : composition.framing;
  }

  // ── 1. Apply aspect checkboxes and pre-fills ──
  $$('.aspect-card').forEach((card) => {
    const key = card.dataset.aspect;
    const isActive = activatedKeys.has(key);
    const checkbox = card.querySelector('input[type=checkbox]');
    if (checkbox) checkbox.checked = isActive;

    if (isActive) {
      // Set priority
      const prioritySelect = card.querySelector('.aspect-priority');
      if (prioritySelect && keyPriorities[key]) {
        const priVal = keyPriorities[key];
        const opts = [...prioritySelect.options].map((o) => o.value);
        // Map: critical → "locked", high → "required", medium → "preferred"
        const priMap = { critical: 'locked', high: 'required', medium: 'preferred', low: 'preferred' };
        const mappedPri = priMap[priVal] || 'required';
        if (opts.includes(mappedPri)) prioritySelect.value = mappedPri;
      }

      // Set description
      const extraInput = card.querySelector('.aspect-extra');
      if (extraInput && keyDescriptions[key]) {
        extraInput.value = keyDescriptions[key];
      }
    }
  });

  // ── 2. Pre-fill aspect source dropdowns from anchor→image mapping ──
  // Map anchor type → (source image number, prioritized)
  const anchorSourceMap = {};  // anchorType → imageNumber (e.g. 2 means "图2")
  for (const a of anchors) {
    if (!a.source) continue;
    if (a.category === 'edit') continue;
    if (a.type === 'object') continue;
    const formKey = TYPE_TO_ASPECT_KEY[a.type];
    if (!formKey) continue;
    // Derive image number from source string (e.g. "图2" → 2, "image_2" → 2)
    let imgNum = 0;
    const m1 = a.source.match(/图(\d+)/);
    const m2 = a.source.match(/image_(\d+)/);
    if (m1) imgNum = parseInt(m1[1]);
    else if (m2) imgNum = parseInt(m2[1]);
    if (!imgNum) continue;

    const priOrder = { critical: 4, high: 3, medium: 2, low: 1 };
    const existingPri = priOrder[anchorSourceMap[formKey + ':pri']] || 0;
    const newPri = priOrder[a.priority] || 0;
    if (!anchorSourceMap[formKey] || newPri > existingPri) {
      anchorSourceMap[formKey] = imgNum;
      anchorSourceMap[formKey + ':pri'] = a.priority;
    }
  }

  // Map image numbers → reference array index for pre-fill
  $$('.aspect-card').forEach((card) => {
    const key = card.dataset.aspect;
    const imgNum = anchorSourceMap[key];
    if (!imgNum) return;
    const srcSel = card.querySelector('.aspect-source');
    if (!srcSel) return;
    const refIdx = store.anchorReferences.findIndex((r, i) => {
      // Try to match: image number vs reference index+1
      return (i + 1) === imgNum;
    });
    if (refIdx >= 0) srcSel.value = String(refIdx);
  });

  // ── 3. Auto-fill negative constraints ──
  const editAnchors = anchors.filter((a) => a.category === 'edit');
  const removeDescs = editAnchors
    .filter((a) => a.operation === 'remove')
    .map((a) => a.description)
    .filter(Boolean);

  if (removeDescs.length) {
    const negEl = $('#anchor-negative');
    const existing = negEl.value.trim();
    const prefix = existing ? existing + '；' : '';
    negEl.value = prefix + '不要：' + removeDescs.join('、');
  }

  // ── 4. Apply extra description ──
  const extraConstraints = schema.extra_constraints || [];
  if (extraConstraints.length) {
    const descEl = $('#anchor-description');
    if (descEl) {
      const existing = descEl.value.trim();
      const prefix = existing ? existing + '；' : '';
      descEl.value = prefix + extraConstraints.join('；');
    }
  }

  const anchorCount = new Set(anchors.filter((a) => a.category !== 'edit' && a.type !== 'object').map((a) => a.type)).size;
  const objCount = objects.length;
  renderAnchorReferences();
  renderAspectSourceSummary();
  scrollTo({ top: $('#anchor-aspects').offsetTop - 20, behavior: 'smooth' });
  toast(`已应用 ${anchorCount} 个视觉属性锚点，来源图已预填${objCount ? `，${objCount} 个独立物体` : ''}`);
}

// ── Quality / Negative Preset Tags ───────────────────────────────────────────

/** Build final text: selected preset labels + manual text */
function buildPresetText(textareaId, presetType) {
  const el = $(textareaId);
  const manual = el ? el.value.trim() : '';
  const selected = [];
  $$(`.preset-tag.selected[data-preset-type="${presetType}"]`).forEach((tag) => {
    selected.push(tag.dataset.label);
  });
  const parts = [];
  if (selected.length) parts.push(selected.join('；'));
  if (manual) parts.push(manual);
  return parts.join('；');
}

/** Render quality preset tags */
export function renderAnchorQualityPresets() {
  renderPresetTags('anchor-quality-presets', store.qualityPresets || {}, 'quality');
}

/** Render negative preset tags */
export function renderAnchorNegativePresets() {
  renderPresetTags('anchor-negative-presets', store.negativePresets || {}, 'negative');
}

function renderPresetTags(containerId, presets, presetType) {
  const container = $(`#${containerId}`);
  if (!container) return;
  const entries = Object.entries(presets);
  if (!entries.length) {
    container.innerHTML = '<span class="muted">暂无预设</span>';
    return;
  }
  container.innerHTML = entries
    .map(([key, label]) =>
      `<span class="preset-tag" data-preset-key="${key}" data-preset-type="${presetType}" data-label="${escapeHtml(label)}" onclick="togglePresetTag(this)">${escapeHtml(label)}</span>`
    )
    .join('');
}

/** Toggle a quality/negative preset tag selection */
function togglePresetTag(el) {
  el.classList.toggle('selected');
}
window.togglePresetTag = togglePresetTag;

/** Restore preset tag selections when editing an existing task */
function restorePresetSelections(description, negative) {
  $$('.preset-tag[data-preset-type="quality"]').forEach((tag) => {
    if (description && description.includes(tag.dataset.label)) {
      tag.classList.add('selected');
    } else {
      tag.classList.remove('selected');
    }
  });
  $$('.preset-tag[data-preset-type="negative"]').forEach((tag) => {
    if (negative && negative.includes(tag.dataset.label)) {
      tag.classList.add('selected');
    } else {
      tag.classList.remove('selected');
    }
  });
}

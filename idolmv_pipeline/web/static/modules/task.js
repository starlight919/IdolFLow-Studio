// Video Task Form & Run Management Module
// ==========================================================================

import store from './state.js';
import { api, post } from './api.js';
import { $, $$, toast, escapeHtml, escapeAttr, formatBytes, modeName, stageName, lines, renderEmptyState } from './utils.js';

// ── Task Folder Relative Path ───────────────────────────────────────────────

export function taskFolderRelative() {
  return $('#task-dir').value.trim();
}

// ── Preview Helpers ─────────────────────────────────────────────────────────

function previewPath(file) {
  const root = taskFolderRelative();
  const path = root ? `${root.replace(/\/$/, '')}/${file}` : file;
  return `/api/file-preview?root=data_root&path=${encodeURIComponent(path)}`;
}

export function renderVideoAssetPreviews() {
  const anchorFiles = lines('#anchors');
  const referenceFiles = lines('#references');

  const anchorEl = $('#anchor-file-previews');
  if (anchorEl) {
    anchorEl.innerHTML = anchorFiles.length
      ? anchorFiles.map((file) => `<figure><img src="${previewPath(file)}" loading="lazy" onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22%3E✗%3C/text%3E%3C/svg%3E'"><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`).join('')
      : '<p class="hint">未选择任何文件</p>';
  }

  const refEl = $('#reference-file-previews');
  if (refEl) {
    refEl.innerHTML = referenceFiles.length
      ? referenceFiles.map((file) => `<figure><video src="${previewPath(file)}#t=0.1" preload="metadata" muted onerror="console.error('Failed to load:',this.src)"></video><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`).join('')
      : '<p class="hint">未选择任何文件</p>';
  }
}

// ── Asset Picker ────────────────────────────────────────────────────────────

export async function openAssetPicker(category) {
  store.assetPickerCategory = category;
  store.assetPickerRoot = taskFolderRelative();
  // For anchor images, default to the anchors/selected/ subdirectory where
  // promoted anchor candidates live.
  store.assetPickerPath = category === 'anchors'
    ? `${store.assetPickerRoot.replace(/\/$/, '')}/anchors/selected`
    : store.assetPickerRoot;
  store.assetPickerSelected = new Set(lines(category === 'anchors' ? '#anchors' : '#references'));
  $('#asset-picker-title').textContent = category === 'anchors' ? '选择 Anchor 图片' : '选择参考视频';
  $('#asset-picker-modal').hidden = false;
  await browseAssets(store.assetPickerPath);
}

export function closeAssetPicker() {
  $('#asset-picker-modal').hidden = true;
}

export async function browseAssets(path) {
  try {
    const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(path)}`);
    store.assetPickerPath = data.path === '.' ? '' : data.path;
    $('#asset-picker-path').textContent = `data_root / ${store.assetPickerPath}`;

    const parent = store.assetPickerPath.split('/').slice(0, -1).join('/');
    const base = store.assetPickerRoot ? store.assetPickerRoot.replace(/\/$/, '') + '/' : '';
    const relative = (item) => (item.path.startsWith(base) ? item.path.slice(base.length) : item.path);
    const allowed = (item) =>
      store.assetPickerCategory === 'references'
        ? /\.(mp4|mov|m4v|webm)$/i.test(item.name)
        : /\.(png|jpe?g|webp)$/i.test(item.name);

    const list = $('#asset-picker-list');
    list.innerHTML =
      (store.assetPickerPath
        ? `<button onclick="browseAssets('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>`
        : '') +
      data.items
        .map((item) =>
          item.directory
            ? `<button onclick="browseAssets('${escapeAttr(item.path)}')"><span>${escapeHtml(item.name)}</span><span>›</span></button>`
            : allowed(item)
              ? `<label class="file-option"><span>${escapeHtml(item.name)}</span><input type="checkbox" value="${escapeHtml(relative(item))}" ${store.assetPickerSelected.has(relative(item)) ? 'checked' : ''} onchange="toggleAsset(this)"></label>`
              : ''
        )
        .join('');
  } catch (e) {
    toast(e.message);
  }
}

export function toggleAsset(input) {
  if (input.checked) {
    store.assetPickerSelected.add(input.value);
  } else {
    store.assetPickerSelected.delete(input.value);
  }
}

export function confirmAssetSelection() {
  if (store.anchorPickerMode) {
    // Import from anchor module dynamically to avoid circular deps
    import('./anchor.js').then(({ renderAnchorReferences, syncAspectSourceDropdowns }) => {
      [...store.assetPickerSelected].forEach((file) => {
        store.anchorReferences.push({
          id: `ref-${store.anchorReferences.length + 1}`,
          file,
          bindings: [],  // No auto-binding — user selects source per aspect in step 3
          note: '',
          remove_watermark: false,
        });
      });
      store.anchorPickerMode = false;
      renderAnchorReferences();
      syncAspectSourceDropdowns();
      closeAssetPicker();
    });
    return;
  }

  const target = store.assetPickerCategory === 'anchors' ? '#anchors' : '#references';
  $(target).value = [...store.assetPickerSelected].join('\n');
  renderVideoAssetPreviews();
  closeAssetPicker();
}

// ── Folder Picker ───────────────────────────────────────────────────────────

export function openFolderPicker() {
  store.folderPath = '';
  $('#folder-modal').hidden = false;
  browseFolder('');
}

export function closeFolderPicker() {
  $('#folder-modal').hidden = true;
}

export async function browseFolder(path) {
  try {
    const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(path)}`);
    store.folderPath = data.path === '.' ? '' : data.path;
    $('#folder-path').textContent = `data_root / ${store.folderPath}`;
    const parent = store.folderPath.split('/').slice(0, -1).join('/');
    $('#folder-list').innerHTML =
      `<div class="folder-new">
        <input id="new-folder-name" type="text" placeholder="新建文件夹名称...">
        <button class="primary" onclick="createFolder()">新建</button>
      </div>` +
      (store.folderPath ? `<button onclick="browseFolder('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>` : '') +
      data.items
        .filter((i) => i.directory)
        .map((i) => `<button onclick="browseFolder('${escapeAttr(i.path)}')"><span>${escapeHtml(i.name)}</span><span>›</span></button>`)
        .join('');
  } catch (e) {
    toast(e.message);
  }
}

export async function createFolder() {
  const input = $('#new-folder-name');
  const name = input.value.trim();
  if (!name) { toast('请输入文件夹名称'); return; }
  try {
    await post('/api/folders', { root: 'data_root', parent: store.folderPath, name });
    input.value = '';
    toast(`文件夹"${name}"已创建`);
    await browseFolder(store.folderPath);
  } catch (e) { toast(e.message); }
}

export async function chooseFolder() {
  const target = store.folderPickerTarget;
  const inputId = target === 'anchor' ? '#anchor-id' : '#task-dir';
  $(inputId).value = store.folderPath || '';
  store.folderPickerTarget = null;
  closeFolderPicker();
}

export function taskFolderName() {
  return $('#task-dir').value.trim();
}

// ── Task Form ───────────────────────────────────────────────────────────────

export function formTask() {
  const name = ($('#task-name')?.value || '').trim();
  const taskDir = $('#task-dir').value.trim();
  if (!name) throw new Error('请输入任务名称');
  if (!taskDir) throw new Error('请选择任务文件夹');
  const dataRoot = store.workspaceSettings?.data_root || '';
  const dirName = taskDir.split('/').pop() || taskDir;
  return {
    name,
    task_dir: dataRoot + '/' + taskDir,
    data_dir: dirName,
    mode: $('[name=mode]:checked').value,
    candidates: Number($('#candidates').value),
    filename_prefix: name,
    anchors: lines('#anchors').map((file, i) => ({ key: `anchor-${i + 1}`, label: `Anchor ${i + 1}`, file })),
    references: (() => {
      const videoRefs = lines('#references');
      const audioRefs = lines('#audio-refs');
      // 当前在音频 tab 下：纯音频模式，不传视频
      const isAudioTab = document.querySelector('.ref-tab.active')?.dataset?.refTab === 'audio';
      if (isAudioTab) {
        return audioRefs.map((file, i) => ({
          name: `reference-${i + 1}`,
          file,
          duration: 15,
          pass_reference_audio: true,
          pass_reference_video: false,
          pad_mode: 'none',
        }));
      }
      // 视频 tab：传视频，可选传音频（从视频提取）
      const padEl = document.getElementById('pad-mode');
      const passAudioEl = document.getElementById('pass-reference-audio');
      return videoRefs.map((file, i) => ({
        name: `reference-${i + 1}`,
        file,
        duration: 15,
        pass_reference_audio: passAudioEl?.checked ?? true,
        pass_reference_video: true,
        pad_mode: padEl?.value || 'none',
        ...(audioRefs[i] ? { audio_file: audioRefs[i] } : {}),
      }));
    })(),
    lyrics: $('#lyrics').value.trim(),
    constraints: $('#constraints').value.trim(),
  };
}

export function switchRefTab(tab) {
  const videoTA = $('#references');
  const audioTA = $('#audio-refs');
  const padRow = $('.pad-mode-row');
  const passAudioWrap = $('#pass-audio-wrap');
  const mode = $('[name=mode]:checked')?.value;
  if (!videoTA || !audioTA) return;
  if (tab === 'video') {
    videoTA.hidden = false;
    audioTA.hidden = true;
    if (padRow) padRow.style.display = '';
    // motion 模式不显示"传参考音频"
    if (passAudioWrap) passAudioWrap.style.display = mode === 'motion' ? 'none' : '';
  } else {
    videoTA.hidden = true;
    audioTA.hidden = false;
    // 音频 tab：隐藏时长对齐 + "传参考音频"（选音频 tab 就是要传音频）
    if (padRow) padRow.style.display = 'none';
    if (passAudioWrap) passAudioWrap.style.display = 'none';
  }
  $$('.ref-tab').forEach(b => b.classList.toggle('active', b.dataset.refTab === tab));
}

export function updateMode() {
  const radio = $('[name=mode]:checked');
  if (!radio) return;
  const mode = radio.value;
  $('#lyrics-wrap').style.display = mode === 'motion' ? 'none' : 'flex';
  // "传参考音频"的显示由当前 ref-tab 决定（switchRefTab），这里只处理 motion 强制不传
  const cb = $('#pass-reference-audio');
  const wrap = $('#pass-audio-wrap');
  if (mode === 'motion' && cb && wrap) {
    wrap.style.display = 'none';
    cb.checked = false;
  }
  // 切换模式后同步当前 ref-tab 的显示状态
  const currentTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab;
  if (currentTab) switchRefTab(currentTab);
  // "传参考视频"选项：lip_sync 通过 ref-tabs 控制（视频/音频 tab），不显示 checkbox
  // dance_lip_sync / motion 强制传视频，也不显示
  const videoWrap = $('#pass-video-wrap');
  if (videoWrap) videoWrap.style.display = 'none';
  // 音频 tab：motion 模式隐藏，对口型模式显示
  const audioTab = document.querySelector('[data-ref-tab="audio"]');
  if (audioTab) audioTab.style.display = mode === 'motion' ? 'none' : '';
  // 如果当前在音频 tab 且切换到了 motion，强制切回视频 tab
  if (mode === 'motion' && audioTab && audioTab.classList.contains('active')) {
    switchRefTab('video');
  }
}

/* ── 时长对齐 tab 切换 ── */
export function switchPadMode(mode) {
  const el = document.getElementById('pad-mode');
  if (el) el.value = mode;
  document.querySelectorAll('[data-pad-mode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.padMode === mode);
  });
}

// ── Auto-Fill ───────────────────────────────────────────────────────────────
// (deprecated — folder name is the sole identifier; kept for backwards compat)

export function autoFillTaskFields(source) {
  // no-op: folder name is the only entry point now
}

export function markAsManuallyEdited(input) {
  input.dataset.autoFilled = 'false';
}

// ── Task CRUD ───────────────────────────────────────────────────────────────

export async function saveTask(event, mode = 'auto') {
  event?.preventDefault();
  const data = formTask();
  const newId = `${data.data_dir}__${data.name}`;
  const editingId = store.currentTask?.id;

  // mode=auto: 编辑已有任务时，让用户选择
  if (mode === 'auto' && editingId && editingId !== newId) {
    showSaveModeDialog(data, editingId);
    return;
  }

  const task = await _doSave(data, editingId, mode);
  store.currentTask = task;
  toast('任务已保存');
  await loadTasks();
  return task;
}

async function _doSave(data, editingId, mode) {
  // mode=update: 先删旧任务再保存（实现"更新"效果）
  if (mode === 'update' && editingId) {
    await api(`/api/tasks/${encodeURIComponent(editingId)}`, 'DELETE');
  }
  // 检查同名任务是否存在
  const existing = store.tasks?.find(t => t.id === `${data.data_dir}__${data.name}`);
  if (existing && mode !== 'update') {
    throw new Error(`同名任务"${data.name}"已存在，请改名或选择更新已有任务`);
  }
  return await post('/api/tasks', data);
}

function showSaveModeDialog(data, editingId) {
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `<div class="modal-card" style="max-width:400px">
    <h3>保存方式</h3>
    <p>你正在编辑已有任务 <strong>${escapeHtml(store.currentTask?.name || '')}</strong>，但修改了名称或文件夹，这会导致创建新任务。</p>
    <div class="actions" style="flex-direction:column;gap:8px">
      <button onclick="this.closest('.modal').remove(); window._saveAsNew?.()" style="width:100%">保存为新任务</button>
      <button class="secondary" onclick="this.closest('.modal').remove(); window._updateExisting?.()" style="width:100%">更新原任务</button>
      <button class="secondary" onclick="this.closest('.modal').remove()" style="width:100%">取消</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
  modal.hidden = false;

  window._saveAsNew = async () => {
    try {
      const task = await _doSave(data, null, 'new');
      store.currentTask = task;
      toast('已保存为新任务');
      await loadTasks();
    } catch (e) { toast(e.message); }
  };
  window._updateExisting = async () => {
    try {
      const task = await _doSave(data, editingId, 'update');
      store.currentTask = task;
      toast('任务已更新');
      await loadTasks();
    } catch (e) { toast(e.message); }
  };
}

export async function loadTasks() {
  store.tasks = await api('/api/tasks');
  const list = $('#task-list');
  if (!list) return;
  const html = store.tasks
    .map(
      (t) => `<article class="task" data-id="${escapeHtml(t.id)}">
        <div><h3>${escapeHtml(t.name || t.id)}</h3><div class="meta">📁 ${escapeHtml(t.data_dir || t.task_dir || '?')} · ${modeName(t.mode)} · ${t.anchors.length} anchors · ${t.candidates} 候选/组合</div></div>
        <div class="actions">
          <button class="secondary" data-action="task-assets">Assets</button>
          <button class="secondary" data-action="task-edit">编辑</button>
          <button data-action="task-run">运行</button>
          <button class="danger" onclick="confirmDeleteTask('${escapeAttr(t.id)}')">删除</button>
        </div>
      </article>`
    )
    .join('');
  list.innerHTML = html || renderEmptyState('📋', '还没有保存任务', '填写表单后点击"保存任务"即可添加');
}

export async function deleteTask(id) {
  // 确认弹窗已由 confirmDeleteTask (app.js) 统一处理，此函数仅执行删除
  try {
    const resp = await fetch(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(body.error || '删除失败');
    }
    toast('任务已删除');
    await loadTasks();
  } catch (e) { toast(`删除失败: ${e.message}`); }
}

export function editTask(id) {
  const t = store.tasks.find((x) => x.id === id);
  if (!t) return;
  store.currentTask = t;
  const nameEl = $('#task-name');
  if (nameEl) nameEl.value = t.name || '';
  const dir = t.data_dir || t.task_dir || '';
  $('#task-dir').value = dir.endsWith('/') ? dir : dir;
  $('#candidates').value = t.candidates;
  $('#anchors').value = t.anchors.map((x) => x.file).join('\n');
  $('#references').value = t.references.map((x) => x.file).join('\n');
  // 默认切到视频 tab（对口型任务视频是主输入；纯音频任务除外）
  const isAudioOnly = t.references?.length > 0 && t.references.every(r => r.pass_reference_video === false);
  if (!isAudioOnly) switchRefTab('video');
  const passAudio = t.references[0]?.pass_reference_audio;
  const passAudioEl = document.getElementById('pass-reference-audio');
  if (passAudioEl) passAudioEl.checked = passAudio !== false;
  const passVideo = t.references[0]?.pass_reference_video;
  const passVideoEl = document.getElementById('pass-reference-video');
  if (passVideoEl) passVideoEl.checked = passVideo !== false;
  const padMode = t.references[0]?.pad_mode || 'none';
  switchPadMode(padMode);
  $('#lyrics').value = t.lyrics || '';
  $('#constraints').value = t.constraints || '';

  const radio = $(`[name=mode][value="${t.mode}"]`);
  if (radio) radio.checked = true;
  $$('.mode').forEach((m) => m.classList.toggle('active', m.contains(radio)));
  updateMode();
  renderVideoAssetPreviews();
  scrollTo({ top: 0, behavior: 'smooth' });
}

export function resetForm() {
  $('#task-form').reset();
  store.currentTask = null;
  $$('.mode').forEach((m, i) => m.classList.toggle('active', i === 0));
  updateMode();
}

export async function showAssets(id) {
  const existing = $('#asset-panel');
  // 已展开且是同一个任务 → 关闭（toggle）
  if (existing && existing.dataset.taskId === id) {
    existing.remove();
    return;
  }
  try {
    const data = await api(`/api/tasks/${encodeURIComponent(id)}/assets`);
    if (existing) existing.remove();
    const card = $(`.task[data-id="${CSS.escape(id)}"]`);
    const panel = document.createElement('div');
    panel.id = 'asset-panel';
    panel.dataset.taskId = id;
    panel.className = 'panel asset-panel-inline';
    panel.innerHTML = `
      <div class="section-head"><h3>Asset 清单</h3></div>
      <div class="asset-list">${data.items.length
        ? data.items
            .map(
              (item) => `<div class="asset-row">
                <div><strong>${escapeHtml(item.key)}</strong><div class="meta">${escapeHtml(item.asset_id)}</div></div>
                <div class="meta">${item.source ? `${escapeHtml(item.source.path)} · ${formatBytes(item.source.size)}` : '无源文件指纹'}</div>
                <button class="text-button danger-text" onclick="clearTaskAssets('${escapeAttr(id)}','${escapeAttr(item.key)}')" title="清除此素材缓存">🗑</button>
              </div>`
            )
            .join('')
        : '<p class="hint">尚无已上传 Asset；首次运行时会按需创建。</p>'}</div>
      <div class="actions"><button class="secondary" onclick="clearTaskAssets('${escapeAttr(id)}')">清除全部缓存</button></div>`;
    if (card) card.after(panel);
    else $('#task-list').after(panel);
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    toast(e.message);
  }
}

export function closeAssets() {
  const panel = $('#asset-panel');
  if (panel) panel.remove();
}

export async function previewPrompt() {
  try {
    const t = formTask();
    const result = await post('/api/prompt-preview', t);
    $('#prompt-preview').hidden = false;
    $('#prompt-preview').textContent = result.prompt;
  } catch (e) {
    toast(e.message);
  }
}

// ── Run Submission ──────────────────────────────────────────────────────────

export function requestStart(id) {
  store.pendingTask = id;
  store.pendingAnchorTask = null;
  $('#submit-password').value = '';
  $('#modal').hidden = false;
  $('#submit-password').focus();
}

export async function startCurrent() {
  try {
    // saveTask 在编辑已有任务且 ID 变化时会弹窗，此时不继续启动
    const data = formTask();
    const newId = `${data.data_dir}__${data.name}`;
    const editingId = store.currentTask?.id;
    if (editingId && editingId !== newId) {
      store._pendingStart = true;
      await saveTask();
      // saveTask 弹窗会通过 _saveAsNew/_updateExisting 保存后调用 loadTasks
      // 但这里拿不到 task，简单处理：不继续启动，用户需手动点启动
      return;
    }
    const task = await saveTask(null, 'auto');
    requestStart(task.id);
  } catch (e) {
    toast(e.message);
  }
}

export function closeModal() {
  $('#modal').hidden = true;
  store.pendingTask = null;
  store.pendingAnchorTask = null;
}

export async function confirmStart() {
  try {
    if (store.pendingAnchorTask) {
      const job = await post('/api/anchor-runs', {
        task_id: store.pendingAnchorTask,
        password: $('#submit-password').value,
      });
      closeModal();
      toast('Anchor 任务已进入生成队列');
      const { showView } = await import('../app.js');
      showView('anchors');
      const { loadAnchorRuns, openAnchorPoll } = await import('./anchor.js');
      await loadAnchorRuns();
      openAnchorPoll();
      return;
    }
    const job = await post('/api/runs', {
      task_id: store.pendingTask,
      password: $('#submit-password').value,
    });
    closeModal();
    toast('任务已进入运行队列');
    const { showView } = await import('../app.js');
    showView('runs');
    await loadRuns();
    openRunPoll();
  } catch (e) {
    toast(e.message);
  }
}

// ── Asset Upload ────────────────────────────────────────────────────────────

export async function uploadAsset() {
  const file = $('#upload-file').files[0];
  const id = $('#task-dir').value.trim();
  if (!file || !id) return toast('请先选择任务文件夹并选择文件');

  const category = $('#upload-category').value;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/uploads');
  xhr.setRequestHeader('X-Task-Id', id);
  xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
  xhr.setRequestHeader('X-Category', category);
  xhr.upload.onprogress = (e) => {
    $('#upload-status').textContent = e.lengthComputable ? `${Math.round((e.loaded / e.total) * 100)}%` : '';
  };
  xhr.onload = () => {
    if (xhr.status < 300) {
      const target = category === 'anchors' ? '#anchors' : '#references';
      $(target).value += `${$(target).value ? '\n' : ''}${category}/${file.name}`;
      $('#upload-status').textContent = '完成';
      renderVideoAssetPreviews();
    } else {
      toast(JSON.parse(xhr.responseText).error);
    }
  };
  xhr.send(file);
}

// ── Runs ────────────────────────────────────────────────────────────────────

export async function loadRuns() {
  store.runs = await api('/api/runs');
  const list = $('#run-list');
  if (!list) return;
  list.innerHTML = store.runs.map(runCard).join('') || renderEmptyState('🚀', '还没有运行记录', '配置并启动一个任务后即可看到进度');
  refreshReviewOptions();
}

function runCard(r) {
  const percent = r.total ? Math.round(((r.completed || 0) / r.total) * 100) : r.status === 'completed' ? 100 : 0;
  const isRunning = ['queued', 'running'].includes(r.status);
  const canReview = r.manifest || r.status === 'running';
  const resumeBtn = r.can_resume ? `<button class="run-resume" onclick="event.stopPropagation(); resumeRun('${escapeAttr(r.run_id)}')" title="重新恢复轮询">↻ 恢复</button>` : '';
  return `<article class="run-card${canReview ? ' clickable' : ''}" data-id="${escapeHtml(r.run_id)}"${canReview ? ` onclick="openRunReview('${escapeAttr(r.run_id)}')"` : ''}>
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
    <button class="run-delete" onclick="event.stopPropagation(); confirmDeleteRun('${escapeAttr(r.run_id)}', this)" title="${isRunning ? '运行中无法删除' : '删除此记录'}" ${isRunning ? 'disabled' : ''}>✕</button>
  </article>`;
}

export function openRunPoll() {
  clearInterval(store.pollTimer);
  store.pollTimer = setInterval(async () => {
    if (!$('#runs').classList.contains('active')) return;
    await loadRuns();
    if (!store.runs.some((r) => ['queued', 'running'].includes(r.status))) clearInterval(store.pollTimer);
  }, 1500);
}

function refreshReviewOptions() {
  // 有 manifest 的 run（已完成/生成中）均可进入审核，实时预览已生成的候选
  const available = store.runs.filter((r) => r.manifest || r.status === 'running');
  const select = $('#review-run');
  if (!select) return;
  const current = select.value;
  select.innerHTML = available
    .map((r) => `<option value="${r.run_id}">${escapeHtml(r.task_name)} · ${r.run_id}${r.status === 'running' ? ' (生成中)' : ''}</option>`)
    .join('');
  if (available.some((r) => r.run_id === current)) {
    select.value = current;
  } else if (available.length > 0) {
    // 之前的选中项不存在了，选第一个（但仅在没有当前审核内容时）
    select.value = '';
  }
}

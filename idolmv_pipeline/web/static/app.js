// IdolFlow Studio — Main Application Entry
// ==========================================================================
//
// Orchestrates all feature modules. Attaches needed functions to `window` for
// HTML inline `onclick` handlers to access.

import store from './modules/state.js';
import { api, post, loadSettings } from './modules/api.js';
import { $, $$, toast, escapeHtml } from './modules/utils.js';
import {
  renderAnchorAspects, renderAnchorReferences, prepareAnchors, saveAnchorTask,
  resetAnchorForm, previewAnchorPrompt, closeAnchorPromptPreview, requestAnchorStart,
  loadAnchorTasks, editAnchorTask, loadAnchorRuns, openAnchorPoll,
  regenerateAnchorBatch, promoteAnchor, useAnchorAsReference,
  toggleAnchorTaskSort,
  pickAnchorReferences, openInlineAnchor, openAnchorFolderPicker, setAnchorSource, setCustomAnchorSource, autoFillAnchorFields,
  removeAnchorReference, syncAspectSourceDropdowns, toggleAnchorWatermark,
  onAspectSourceChange, checkAnchorRefDir, scrollToAnchorDir,
  runPromptOptimizer, applyOptimizerResult,
  toggleRefAspectBinding, updateAnchorNote, deleteAnchorTask, recoverAnchorTask,
  renderAnchorQualityPresets, renderAnchorNegativePresets,
  loadAnchorReview,
  toggleAnchorRunSort,
  // Review
} from './modules/anchor.js';
import {
  taskFolderRelative, checkTaskFolderEmpty, goGenerateAnchor, goGenerateReference, addCustomReference, renderCustomRefs, setCustomRefRole, removeCustomRef, onCustomRoleChange, resetCustomRole, toggleCustomAudio, toggleAssetAudio, renderCustomAnchorRefs, removeCustomAnchor, renderVideoAssetPreviews, openAssetPicker, closeAssetPicker,
  browseAssets, toggleAsset, confirmAssetSelection, switchPickerTab, handlePickerUploadFiles, openFolderPicker, closeFolderPicker,
  browseFolder, chooseFolder, createFolder, confirmDeleteDataDir, formTask, updateMode, switchRefTab, switchPadMode, autoFillTaskFields,
  markAsManuallyEdited, saveTask, loadTasks, editTask, resetForm, showAssets, toggleTaskSort,
  onCustomAnchorRoleChange, setCustomAnchorRole, resetCustomAnchorRole,
  closeAssets, previewPrompt, closePromptPreview, markPromptEdited, resetPromptToAuto, requestStart, startCurrent, closeModal, confirmStart, toggleTaskGroup,
  loadRuns, openRunPoll, toggleRunSort,
  openLyricsTimestampsEditor, closeLyricsTimestampsEditor, addTimestamp, resetTimestamps,
  saveLyricsTimestampsFromModal, previewLyricsTimestamps, onLyricsTimestampsKey, showLyricsShortcuts,
  removeVideoAsset, initCustomPromptTemplates, applyCustomPromptTemplate,
} from './modules/task.js';
import { prepareReview, loadReview, renderReview } from './modules/review.js';

// ── Theme (dark / light) toggle ──────────────────────────────────────────────

const THEME_KEY = 'idolflow-theme';

function currentTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'dark' || saved === 'light') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = $('#theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️ 浅色' : '🌙 深色';
}

export function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

export function initTheme() {
  applyTheme(currentTheme());
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
}

// ── Unified Delete Confirm Dialog ────────────────────────────────────────────

let deleteResolver = null;

export function closeDeleteModal() {
  $('#delete-modal').hidden = true;
  if (deleteResolver) { deleteResolver(false); deleteResolver = null; }
}

function showDeleteConfirm({ title, desc, htmlDesc, showFileOption = true, confirmText = '确认删除', danger = true }) {
  return new Promise((resolve) => {
    const confirmBtn = $('#delete-confirm');
    if (!confirmBtn) {
      // HTML 被浏览器缓存，降级为原生 confirm
      resolve(confirm(`${title}\n\n${(desc || '').replace(/<br>/g, '\n')}`));
      return;
    }
    deleteResolver = resolve;
    $('#delete-modal-title').textContent = title;
    // htmlDesc 用于需要富文本（级联树等）的场景，由调用方保证已转义安全
    $('#delete-modal-desc').innerHTML = htmlDesc || escapeHtml(desc).replace(/\n/g, '<br>');
    confirmBtn.textContent = confirmText;
    confirmBtn.classList.toggle('danger', danger);
    const fileLabel = $('#delete-files-label');
    const fileCheckbox = $('#delete-remove-files');
    fileCheckbox.checked = false;
    fileLabel.hidden = !showFileOption;
    $('#delete-modal').hidden = false;
    confirmBtn.focus();
  });
}

export function confirmDeleteAction() {
  if (deleteResolver) { deleteResolver(true); deleteResolver = null; }
  $('#delete-modal').hidden = true;
  // 重置按钮文案，避免影响下次删除确认
  const confirmBtn = $('#delete-confirm');
  if (confirmBtn) { confirmBtn.textContent = '确认删除'; confirmBtn.classList.add('danger'); }
}

export { showDeleteConfirm };

// 兜底：addEventListener 也绑定（防止 inline onclick 因某些原因不生效）
try {
  $('#delete-cancel').addEventListener('click', closeDeleteModal);
  $('#delete-confirm').addEventListener('click', confirmDeleteAction);
  // 遮罩点击关闭已统一由 setupModalAccessibility 处理
} catch {}

function shouldRemoveFiles() {
  return $('#delete-remove-files').checked;
}

// ── Run Delete ──────────────────────────────────────────────────────────────

async function confirmDeleteRun(runId, btn) {
  // 查找 run 信息以确定类型和显示详情
  const videoRun = store.runs?.find((r) => r.run_id === runId);
  const anchorRun = store.anchorRuns?.find((r) => r.run_id === runId);
  const run = videoRun || anchorRun;
  const runType = videoRun ? 'video' : (anchorRun ? 'anchor' : 'unknown');
  const taskName = run?.task_name || runId;
  const outputPath = run?.task_id || '';

  const title = `确认删除运行记录`;
  const desc = `任务: ${escapeHtml(taskName)}\n运行: ${runId}\n\n删除后无法恢复。生成文件位于 runtime/outputs/ 下。`;
  const confirmed = await showDeleteConfirm({ title, desc, showFileOption: true });
  if (!confirmed) return;

  btn.disabled = true;
  btn.textContent = '...';
  const removeFiles = shouldRemoveFiles();
  try {
    let resp;
    if (runType === 'video') {
      const qs = removeFiles ? '?remove_files=1' : '';
      resp = await fetch(`/api/runs/${encodeURIComponent(runId)}${qs}`, { method: 'DELETE' });
    } else {
      // Try video run first, then anchor run (fallback for unknown type)
      const qs = removeFiles ? '?remove_files=1' : '';
      resp = await fetch(`/api/runs/${encodeURIComponent(runId)}${qs}`, { method: 'DELETE' });
      if (!resp.ok && resp.status === 404) {
        resp = await fetch(`/api/anchor-runs/${encodeURIComponent(runId)}${qs}`, { method: 'DELETE' });
      }
    }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(body.error || '删除失败');
    }
    toast(removeFiles ? '运行记录和生成文件已删除' : '运行记录已删除');
    try {
      await loadRuns();
      await loadAnchorRuns();
    } catch {
      // 刷新列表失败不影响删除结果，静默处理
      console.warn('Failed to refresh runs after delete');
    }
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
    btn.textContent = '✕';
  }
}

async function confirmDeleteTask(id) {
  const task = store.tasks?.find((t) => t.id === id);
  const taskName = task?.name || id;
  const dataDir = task?.data_dir || '';
  const runCount = (store.runs || []).filter((r) => r.task_id === id).length;

  const title = `确认删除任务`;
  const desc = `任务: ${escapeHtml(taskName)}\n任务文件夹: ${escapeHtml(dataDir || '(未设置)')}\n关联运行: ${runCount} 条\n\n删除后任务配置将被移除。${runCount > 0 ? '还可选择同时清理关联的运行记录和生成文件。' : ''}`;
  const confirmed = await showDeleteConfirm({ title, desc, showFileOption: true });
  if (!confirmed) return;

  try {
    const removeFiles = shouldRemoveFiles();
    const qs = removeFiles ? '?remove_files=1' : '';
    await fetch(`/api/tasks/${encodeURIComponent(id)}${qs}`, { method: 'DELETE' });
    toast(removeFiles ? '任务及相关文件已删除' : '任务已删除');
    await loadTasks();
    await loadRuns();
  } catch (e) { toast(e.message); }
}

async function confirmDeleteAnchorTask(id) {
  const title = `确认删除 Anchor 任务`;
  const desc = `任务文件夹: ${escapeHtml(id)}\n\n删除后将移除 anchors/ 子目录（含参考图、生成候选、已选图片）。此操作不可撤销。`;
  const confirmed = await showDeleteConfirm({ title, desc, showFileOption: false });
  if (!confirmed) return;

  try {
    await fetch(`/api/anchor-tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast(`已删除: ${id}`);
    await loadAnchorTasks();
  } catch (e) { toast(`删除失败: ${e.message}`); }
}

// ── Navigation ──────────────────────────────────────────────────────────────

export async function showView(id) {
  $$('nav button').forEach((b) => b.classList.toggle('active', b.dataset.view === id));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === id));

  if (id === 'anchors') await prepareAnchors();
  if (id === 'runs') await loadRuns();
  if (id === 'review') await prepareReview();
}

export async function openRunReview(runId) {
  await showView('review');
  const select = $('#review-run');
  if (select) {
    select.value = runId;
    loadReview(runId);
  }
}

export async function openAnchorRunReview(runId) {
  await showView('anchors');
  const select = $('#anchor-review-run');
  if (select) {
    select.value = runId;
    // Scroll to the review section
    const reviewSection = select.closest('.section-head')?.nextElementSibling;
    if (reviewSection) reviewSection.scrollIntoView({ behavior: 'smooth' });
    // Dynamic import to avoid circular dependency
    const { loadAnchorReview } = await import('./modules/anchor.js');
    loadAnchorReview(runId);
  }
}

export async function resumeRun(runId) {
  try {
    await post(`/api/runs/${encodeURIComponent(runId)}/resume`);
    toast('已提交恢复，正在重新轮询...');
    await loadRuns();
  } catch (e) { toast(`恢复失败: ${e.message}`); }
}

export async function resumeAnchorRun(runId) {
  try {
    await post(`/api/anchor-runs/${encodeURIComponent(runId)}/resume`);
    toast('已提交恢复，正在重新轮询...');
    await loadAnchorRuns();
  } catch (e) { toast(`恢复失败: ${e.message}`); }
}

export async function clearTaskAssets(taskId, category) {
  try {
    const qs = category ? `?category=${encodeURIComponent(category)}` : '';
    const resp = await post(`/api/tasks/${encodeURIComponent(taskId)}/clear-assets${qs}`);
    const msg = category
      ? `已清除素材缓存: ${resp.removed?.length || 0} 条`
      : '素材缓存已全部清除，下次提交将重新上传';
    toast(msg);
    // 刷新 asset 面板
    const { showAssets } = await import('./modules/task.js');
    await showAssets(taskId);
  } catch (e) { toast(`清除失败: ${e.message}`); }
}

// ── Delegated Click Handlers ────────────────────────────────────────────────

function setupDelegatedHandlers() {
  document.addEventListener('click', (e) => {
    const target = e.target;

    // Navigation buttons
    if (target.matches('nav button[data-view]')) {
      showView(target.dataset.view);
      return;
    }

    // Mode radio buttons
    if (target.matches('[name=mode]')) {
      updateMode();
      $$('.mode').forEach((m) => m.classList.toggle('active', m.contains(target)));
      return;
    }

    // ── Anchor review toolbar ──
    if (target.closest('[data-action="anchor-regenerate"]')) {
      regenerateAnchorBatch();
      return;
    }

    // ── Anchor review card buttons ──
    const anchorCard = target.closest('.anchor-review-card[data-id]');
    if (anchorCard) {
      const id = anchorCard.dataset.id;
      if (target.closest('[data-action="anchor-promote"]')) {
        promoteAnchor(id);
        return;
      }
      if (target.closest('[data-action="anchor-use-as-reference"]')) {
        useAnchorAsReference(id);
        return;
      }
    }

    // ── Review card (no vote buttons, only download) ──

    // ── Asset preview / chip remove (✕) buttons ──
    if (target.closest('.asset-remove, .chip-remove')) {
      const btn = target.closest('.asset-remove, .chip-remove');
      removeVideoAsset(btn.dataset.type, btn.dataset.file);
      return;
    }

    // ── Task / Anchor task card buttons ──
    const actionBtn = target.closest('[data-action]');
    if (actionBtn) {
      const card = actionBtn.closest('[data-id]');
      if (!card) return;
      const id = card.dataset.id;
      const action = actionBtn.dataset.action;

      if (action === 'task-assets') { showAssets(id); return; }
      if (action === 'task-edit') { editTask(id); return; }
      if (action === 'task-run') { requestStart(id); return; }
      if (action === 'task-delete') { confirmDeleteTask(id); return; }
      if (action === 'anchor-edit') { editAnchorTask(id); return; }
      if (action === 'anchor-start') {
        store.pendingAnchorTask = id;
        store.pendingTask = null;
        $('#submit-password').value = '';
        $('#modal').hidden = false;
        $('#submit-password').focus();
        return;
      }
      if (action === 'anchor-delete') { confirmDeleteAnchorTask(id); return; }
    }
  });
}

// ── Help modal ──────────────────────────────────────────────────────────────

function openHelp() {
  const modal = $('#help-modal');
  if (modal) modal.hidden = false;
}
function closeHelp() {
  const modal = $('#help-modal');
  if (modal) modal.hidden = true;
  try { localStorage.setItem('seen-help', '1'); } catch (e) {}
}
// 首次访问自动弹出帮助
function maybeShowHelpOnFirstVisit() {
  try {
    if (!localStorage.getItem('seen-help')) openHelp();
  } catch (e) {}
}

// ── Expose to `window` for HTML inline onclick handlers ─────────────────────

Object.assign(window, {
  showView, openRunReview, openAnchorRunReview, resumeRun, resumeAnchorRun, clearTaskAssets, updateMode, switchRefTab, switchPadMode,
  openHelp, closeHelp,
  // Task
  openAssetPicker, closeAssetPicker, browseAssets, toggleAsset, confirmAssetSelection,
  switchPickerTab, handlePickerUploadFiles, toggleTaskGroup,
  openFolderPicker, closeFolderPicker, browseFolder, chooseFolder, createFolder, confirmDeleteDataDir,
  renderVideoAssetPreviews, removeVideoAsset, autoFillTaskFields, markAsManuallyEdited,
  initCustomPromptTemplates, applyCustomPromptTemplate,
  goGenerateAnchor, goGenerateReference, renderCustomRefs, setCustomRefRole, onCustomRoleChange, resetCustomRole, toggleCustomAudio, toggleAssetAudio, removeCustomRef, renderCustomAnchorRefs, removeCustomAnchor, checkTaskFolderEmpty,
  onCustomAnchorRoleChange, setCustomAnchorRole, resetCustomAnchorRole,
  saveTask, loadTasks, editTask, resetForm, showAssets, closeAssets, toggleTaskSort,
  confirmDeleteRun, confirmDeleteTask, confirmDeleteAnchorTask, closeDeleteModal, confirmDeleteAction, showDeleteConfirm,
  previewPrompt, closePromptPreview, markPromptEdited, resetPromptToAuto, requestStart, startCurrent, closeModal, confirmStart,
  loadRuns, openRunPoll, toggleRunSort,
  openLyricsTimestampsEditor, showLyricsShortcuts,
  // Lightbox
  closeImageLightbox,
  // Anchor
  renderAnchorReferences, saveAnchorTask, resetAnchorForm, previewAnchorPrompt, closeAnchorPromptPreview,
  requestAnchorStart, loadAnchorTasks, editAnchorTask,
  loadAnchorRuns, openAnchorPoll, regenerateAnchorBatch, toggleAnchorRunSort,
  promoteAnchor, useAnchorAsReference, toggleAnchorTaskSort,
  pickAnchorReferences, openInlineAnchor, openAnchorFolderPicker, setAnchorSource, setCustomAnchorSource, autoFillAnchorFields,
  removeAnchorReference, syncAspectSourceDropdowns, toggleAnchorWatermark,
  onAspectSourceChange, checkAnchorRefDir, scrollToAnchorDir,
  runPromptOptimizer, applyOptimizerResult,
  toggleRefAspectBinding, updateAnchorNote, deleteAnchorTask, recoverAnchorTask,
  renderAnchorQualityPresets, renderAnchorNegativePresets,
  loadAnchorReview,
  // Review
  loadReview,
  // Utils exposed for inline use
  toast, $, taskFolderRelative,
});

// ── Bootstrap ───────────────────────────────────────────────────────────────

// ── Modal accessibility: 统一 ESC 关闭 + 遮罩点击关闭 + 焦点陷阱 ────────────

// 各模态框 id → 关闭函数（ESC 关闭 + 遮罩点击关闭统一走这里）
const MODAL_CLOSE_FNS = {
  'asset-picker-modal': closeAssetPicker,
  'folder-modal': closeFolderPicker,
  'modal': closeModal,
  'delete-modal': closeDeleteModal,
  'help-modal': closeHelp,
  'lyrics-timestamps-modal': closeLyricsTimestampsEditor,
  'image-lightbox': closeImageLightbox,
};

function visibleModal() {
  for (const id of Object.keys(MODAL_CLOSE_FNS)) {
    const el = document.getElementById(id);
    if (el && !el.hidden) return el;
  }
  return null;
}

function closeTopModal() {
  const el = visibleModal();
  if (!el) return;
  MODAL_CLOSE_FNS[el.id]?.();
}

// 焦点陷阱：Tab 循环锁定在可见 modal 内
function trapFocus(e) {
  const modal = visibleModal();
  if (!modal) return;
  const focusables = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (focusables.length === 0) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function onGlobalKeydown(e) {
  if (e.key === 'Escape') {
    // 关闭当前可见的顶层 modal（符合 ESC 关闭 dialog 的通用惯例）
    closeTopModal();
  } else if (e.key === 'Tab') {
    trapFocus(e);
  }
}

function setupModalAccessibility() {
  document.addEventListener('keydown', onGlobalKeydown);
  // 遮罩点击关闭：点击 modal 本身（非内部卡片）时关闭
  document.addEventListener('click', (e) => {
    const modal = e.target.closest?.('.modal');
    if (modal && e.target === modal && MODAL_CLOSE_FNS[modal.id]) {
      MODAL_CLOSE_FNS[modal.id]();
    }
  });
}

// ── 媒体预览 Lightbox（图片 / 音频 / 视频）───────────────────────────────────
// 覆盖主页面素材图（#anchor-file-previews / #reference-file-previews）、
// Anchor 参考图卡片、asset picker 缩略图。用捕获阶段委托，以便在
// Anchor 参考图卡片的 inline onclick（toggleRefExpand，冒泡阶段）之前拦截点击。
function setupImageLightbox() {
  // 点击遮罩背景关闭；图片本身也可点关闭（toggle 习惯）；
  // 音频/视频播放器本体不关闭（便于操作进度条等控件）。
  // 阻止冒泡，避免关闭后触发其他委托逻辑。
  const boxEl = $('#image-lightbox');
  if (boxEl) {
    boxEl.addEventListener('click', (e) => {
      e.stopPropagation();
      const t = e.target;
      // 图片本身可点关闭（toggle 习惯）；
      // 音频/视频播放器本体（.lightbox-audio/.lightbox-video）不关闭，便于操作进度条等控件；
      // 点击遮罩背景或 .lightbox-media 空白处也关闭。
      const clickOnImg = t.classList?.contains('lightbox-img');
      const clickOnPlayer = t.classList?.contains('lightbox-audio') || t.classList?.contains('lightbox-video');
      const clickOnBackdrop = t === boxEl || t.classList?.contains('lightbox-media') || t.id === 'lightbox-caption';
      if (!clickOnPlayer && (clickOnBackdrop || clickOnImg)) {
        closeImageLightbox();
      }
    });
  }
  document.addEventListener('click', (e) => {
    const target = e.target;
    // 点击删除按钮（✕）等操作控件时，不触发预览
    if (target.closest('.asset-remove, .chip-remove, .lightbox-close')) return;
    // Anchor 参考图卡片的缩略图点击仅放大，不触发展开/收起
    const refThumb = target.closest('.reference-thumb');
    if (refThumb) {
      e.preventDefault(); e.stopPropagation();
      openImageLightbox(refThumb.currentSrc || refThumb.src, '点击空白处或按 ESC 关闭');
      return;
    }
    // 音频缩略图（♪ 图标或其所在卡片）
    const audioFig = target.closest('.asset-figure.asset-audio, .asset-audio-icon');
    if (audioFig) {
      // preventDefault 阻止 <label> 包裹导致点击缩略图默认激活其内第一个按钮（如"现场生成"/"视频"tab）
      e.preventDefault(); e.stopPropagation();
      const fig = audioFig.classList.contains('asset-audio-icon') ? audioFig.closest('.asset-figure') : audioFig;
      const file = fig?.dataset.file;
      if (file) openMediaLightbox('audio', file, fig?.querySelector('figcaption')?.textContent?.trim() || '');
      return;
    }
    // 视频缩略图（<video> 元素或其父级）
    const vid = target.closest('.asset-figure video');
    if (vid) {
      e.preventDefault(); e.stopPropagation();
      const fig = vid.closest('.asset-figure');
      const file = fig?.dataset.file;
      if (file) openMediaLightbox('video', file, fig?.querySelector('figcaption')?.textContent?.trim() || '');
      return;
    }
    // 图片缩略图
    const img = target.closest('.asset-figure img, .file-thumb, .anchor-review-card img');
    if (!img) return;
    e.preventDefault(); e.stopPropagation();
    const figcap = img.closest('figcaption');
    const meta = img.closest('.review-meta')?.textContent?.trim();
    openImageLightbox(img.currentSrc || img.src, figcap?.textContent?.trim() || meta || '');
  }, true); // capture=true 提前拦截
}

function _mediaPreviewUrl(file) {
  // file 是相对 data_root 的路径，与预览缩略图同一接口
  return `/api/file-preview?root=data_root&path=${encodeURIComponent(file)}`;
}

function openImageLightbox(src, caption = '') {
  const mediaEl = $('#lightbox-media');
  if (!mediaEl || !src) return;
  mediaEl.innerHTML = `<img src="${src}" alt="" draggable="false" class="lightbox-img">`;
  _showLightbox(caption);
}

// 打开音频/视频预览：type = 'audio' | 'video'，file 为相对任务文件夹路径
function openMediaLightbox(type, file, caption = '') {
  const mediaEl = $('#lightbox-media');
  if (!mediaEl || !file) return;
  // file 是相对任务文件夹（task_dir）的路径，需补上前缀，
  // 与缩略图 previewPath 的拼法一致，否则后端按 data_root 直接解析会 404。
  const root = (typeof taskFolderRelative === 'function' ? taskFolderRelative() : '').replace(/\/$/, '');
  const fullPath = root ? `${root}/${file}` : file;
  const url = _mediaPreviewUrl(fullPath);
  const controls = type === 'video' ? 'controls' : 'controls autoplay';
  const tag = type === 'video' ? 'video' : 'audio';
  mediaEl.innerHTML = `<${tag} class="lightbox-${type}" src="${url}" ${controls} preload="metadata"></${tag}>`;
  _showLightbox(caption);
}

function _showLightbox(caption = '') {
  const box = $('#image-lightbox');
  if (!box) return;
  const cap = $('#lightbox-caption');
  if (cap) cap.textContent = caption;
  box.hidden = false;
}

function closeImageLightbox() {
  const box = $('#image-lightbox');
  if (!box) return;
  box.hidden = true;
  const mediaEl = $('#lightbox-media');
  if (mediaEl) {
    // 停止音频/视频播放
    const media = mediaEl.querySelector('audio, video');
    if (media) { try { media.pause(); } catch {} }
    mediaEl.innerHTML = '';
  }
}

async function init() {
  initTheme();
  setupDelegatedHandlers();
  setupModalAccessibility();
  setupImageLightbox();
  initCustomPromptTemplates();
  updateMode();
  store.workspaceSettings = await loadSettings();
  // 绑定表单提交（type=submit 按钮需要 form submit 事件才能调用保存逻辑）
  const taskForm = $('#task-form');
  if (taskForm) taskForm.addEventListener('submit', (e) => saveTask(e));
  const anchorForm = $('#anchor-form');
  if (anchorForm) anchorForm.addEventListener('submit', (e) => saveAnchorTask(e));
  const openTsBtn = $('#open-lyrics-timestamps');
  if (openTsBtn) openTsBtn.addEventListener('click', openLyricsTimestampsEditor);
  // 任务文件夹变化时检测目录内是否已有素材：
  // change（选择器回填/失焦）立即检测；手动输入走 input + 防抖，边输边反馈
  let _dirCheckTimer = null;
  $('#task-dir')?.addEventListener('change', () => { clearTimeout(_dirCheckTimer); checkTaskFolderEmpty(); });
  $('#task-dir')?.addEventListener('input', () => {
    clearTimeout(_dirCheckTimer);
    _dirCheckTimer = setTimeout(checkTaskFolderEmpty, 500);
  });
  checkTaskFolderEmpty();
  checkAnchorRefDir();
  // 智能解析输入一旦改动，之前的解析结果即失效，禁用「应用解析结果」按钮
  $('#optimizer-input')?.addEventListener('input', () => {
    window._lastOptimizerResult = null;
    const applyBtn = $('#optimizer-apply-btn');
    if (applyBtn) applyBtn.disabled = true;
  });
  $('#close-lyrics-timestamps')?.addEventListener('click', closeLyricsTimestampsEditor);
  // 遮罩点击关闭已统一由 setupModalAccessibility 处理
  $('#add-timestamp-btn')?.addEventListener('click', addTimestamp);
  $('#reset-timestamps-btn')?.addEventListener('click', resetTimestamps);
  $('#save-lyrics-timestamps-btn')?.addEventListener('click', saveLyricsTimestampsFromModal);
  $('#preview-lyrics-btn')?.addEventListener('click', previewLyricsTimestamps);
  document.addEventListener('keydown', onLyricsTimestampsKey);
  await Promise.all([loadTasks(), loadRuns(), prepareAnchors()]);
  openRunPoll();
  maybeShowHelpOnFirstVisit();
}

document.addEventListener('DOMContentLoaded', init);

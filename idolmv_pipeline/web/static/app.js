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
  resetAnchorForm, previewAnchorPrompt, requestAnchorStart, uploadAnchorReference,
  loadAnchorTasks, editAnchorTask, loadAnchorRuns, openAnchorPoll,
  regenerateAnchorBatch, anchorVote, promoteAnchor, promoteSelectedAnchors,
  pickAnchorReferences, openInlineAnchor, openAnchorFolderPicker, setAnchorSource, autoFillAnchorFields,
  removeAnchorReference, syncAspectSourceDropdowns, toggleAnchorWatermark,
  onAspectSourceChange,
  toggleRefAspectBinding, deleteAnchorTask, recoverAnchorTask,
  renderAnchorQualityPresets, renderAnchorNegativePresets,
  loadAnchorReview,
  // Review
} from './modules/anchor.js';
import {
  taskFolderRelative, renderVideoAssetPreviews, openAssetPicker, closeAssetPicker,
  browseAssets, toggleAsset, confirmAssetSelection, openFolderPicker, closeFolderPicker,
  browseFolder, chooseFolder, createFolder, formTask, updateMode, switchRefTab, switchPadMode, autoFillTaskFields,
  markAsManuallyEdited, saveTask, loadTasks, editTask, deleteTask, resetForm, showAssets,
  closeAssets, previewPrompt, requestStart, startCurrent, closeModal, confirmStart,
  uploadAsset, loadRuns, openRunPoll,
} from './modules/task.js';
import { prepareReview, loadReview, renderReview } from './modules/review.js';

// ── Unified Delete Confirm Dialog ────────────────────────────────────────────

let deleteResolver = null;

export function closeDeleteModal() {
  $('#delete-modal').hidden = true;
  if (deleteResolver) { deleteResolver(false); deleteResolver = null; }
}

function showDeleteConfirm({ title, desc, showFileOption = true }) {
  return new Promise((resolve) => {
    const confirmBtn = $('#delete-confirm');
    if (!confirmBtn) {
      // HTML 被浏览器缓存，降级为原生 confirm
      resolve(confirm(`${title}\n\n${desc.replace(/<br>/g, '\n')}`));
      return;
    }
    deleteResolver = resolve;
    $('#delete-modal-title').textContent = title;
    $('#delete-modal-desc').innerHTML = escapeHtml(desc).replace(/\n/g, '<br>');
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
}

// 兜底：addEventListener 也绑定（防止 inline onclick 因某些原因不生效）
try {
  $('#delete-cancel').addEventListener('click', closeDeleteModal);
  $('#delete-confirm').addEventListener('click', confirmDeleteAction);
  $('#delete-modal').addEventListener('click', (e) => {
    if (e.target === $('#delete-modal')) closeDeleteModal();
  });
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
  const desc = `任务: ${escapeHtml(taskName)}\n数据目录: ${escapeHtml(dataDir || '(未设置)')}\n关联运行: ${runCount} 条\n\n删除后任务配置将被移除。${runCount > 0 ? '还可选择同时清理关联的运行记录和生成文件。' : ''}`;
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
  const desc = `数据目录: ${escapeHtml(id)}\n\n删除后将移除 anchors/ 子目录（含参考图、生成候选、已选图片）。此操作不可撤销。`;
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
    if (target.closest('[data-action="anchor-promote-selected"]')) {
      promoteSelectedAnchors();
      return;
    }

    // ── Anchor review card buttons ──
    const anchorCard = target.closest('.anchor-review-card[data-id]');
    if (anchorCard) {
      const id = anchorCard.dataset.id;
      if (target.closest('[data-action="anchor-vote"]')) {
        anchorVote(id, target.closest('[data-action="anchor-vote"]').dataset.vote, target.closest('[data-action="anchor-vote"]'));
        return;
      }
      if (target.closest('[data-action="anchor-promote"]')) {
        promoteAnchor(id);
        return;
      }
    }

    // ── Review card (no vote buttons, only download) ──

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
  openFolderPicker, closeFolderPicker, browseFolder, chooseFolder, createFolder,
  renderVideoAssetPreviews, autoFillTaskFields, markAsManuallyEdited,
  saveTask, loadTasks, editTask, deleteTask, resetForm, showAssets, closeAssets,
  confirmDeleteRun, confirmDeleteTask, confirmDeleteAnchorTask, closeDeleteModal, confirmDeleteAction,
  previewPrompt, requestStart, startCurrent, closeModal, confirmStart,
  uploadAsset, loadRuns, openRunPoll,
  // Anchor
  renderAnchorReferences, saveAnchorTask, resetAnchorForm, previewAnchorPrompt,
  requestAnchorStart, uploadAnchorReference, loadAnchorTasks, editAnchorTask,
  loadAnchorRuns, openAnchorPoll, regenerateAnchorBatch,
  anchorVote, promoteAnchor, promoteSelectedAnchors,
  pickAnchorReferences, openInlineAnchor, openAnchorFolderPicker, setAnchorSource, autoFillAnchorFields,
  removeAnchorReference, syncAspectSourceDropdowns, toggleAnchorWatermark,
  onAspectSourceChange,
  toggleRefAspectBinding, deleteAnchorTask, recoverAnchorTask,
  renderAnchorQualityPresets, renderAnchorNegativePresets,
  loadAnchorReview,
  // Review
  loadReview,
  // Utils exposed for inline use
  toast, $, taskFolderRelative,
});

// ── Bootstrap ───────────────────────────────────────────────────────────────

async function init() {
  setupDelegatedHandlers();
  updateMode();
  store.workspaceSettings = await loadSettings();
  // 绑定表单提交（type=submit 按钮需要 form submit 事件才能调用保存逻辑）
  const taskForm = $('#task-form');
  if (taskForm) taskForm.addEventListener('submit', (e) => saveTask(e));
  const anchorForm = $('#anchor-form');
  if (anchorForm) anchorForm.addEventListener('submit', (e) => saveAnchorTask(e));
  await Promise.all([loadTasks(), loadRuns(), prepareAnchors()]);
  openRunPoll();
  maybeShowHelpOnFirstVisit();
}

document.addEventListener('DOMContentLoaded', init);

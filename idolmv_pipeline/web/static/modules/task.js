// Video Task Form & Run Management Module
// ==========================================================================

import store from './state.js';
import { api, post, extractTaskAudio, extractAudioByPath, getLyricsTimestamps, saveLyricsTimestamps } from './api.js';
import { $, $$, toast, escapeHtml, escapeAttr, formatBytes, modeName, stageName, lines, renderEmptyState } from './utils.js';

// ── Task Folder Relative Path ───────────────────────────────────────────────

export function taskFolderRelative() {
  return $('#task-dir').value.trim();
}

// ── Task Folder Empty Detection ─────────────────────────────────────────────
// 新建/选择任务目录后，检测目录内是否已有素材（图片/视频/音频），
// 若为空则提示用户去下方上传，或自行把文件放入任务目录。

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif']);
const AV_EXTENSIONS = new Set([
  'mp4', 'mov', 'm4v', 'webm', 'avi', 'mkv',   // 视频
  'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg',   // 音频
]);

// 返回目录内是否已有图片 / 音视频。只下钻已知素材子目录，避免深挖 tasks/seedance 等无关目录。
const ASSET_SUBDIR_RE = /^(anchors?|references?|audio|videos?|images?|assets?|anchor-references|generated)$/i;

async function _scanFolderHasAssets(rel, depth = 0) {
  if (depth > 2) return { hasImage: false, hasAV: false };
  const data = await api(`/api/files?root=data_root&path=${encodeURIComponent(rel)}`);
  const items = data.items || [];
  let hasImage = false;
  let hasAV = false;
  for (const item of items) {
    if (item.directory) {
      // 仅下钻已知素材子目录，且限制深度（不能见到 anchors/ 目录名就认定有图片，
      // 否则新建文件夹时自动建的空 anchors/ 会被误判为「已有图片」）
      if (ASSET_SUBDIR_RE.test(item.name)) {
        const sub = await _scanFolderHasAssets(`${rel.replace(/\/$/, '')}/${item.name}`, depth + 1);
        hasImage = hasImage || sub.hasImage;
        hasAV = hasAV || sub.hasAV;
      }
      continue;
    }
    const ext = (item.name.split('.').pop() || '').toLowerCase();
    if (IMAGE_EXTENSIONS.has(ext)) hasImage = true;
    else if (AV_EXTENSIONS.has(ext)) hasAV = true;
  }
  return { hasImage, hasAV };
}

export async function checkTaskFolderEmpty() {
  const tip = $('#empty-folder-tip');
  const needDirTip = $('#need-dir-tip');
  const rel = taskFolderRelative();
  updateUploadState();
  if (!rel) {
    // 未确定任务文件夹：提示先建立，而非「缺少素材」
    if (tip) tip.hidden = true;
    if (needDirTip) needDirTip.hidden = false;
    return;
  }
  if (needDirTip) needDirTip.hidden = true;
  if (!tip) return;
  try {
    const { hasImage, hasAV } = await _scanFolderHasAssets(rel);
    const missingImage = !hasImage;
    const missingAV = !hasAV;
    // 两类素材都齐 → 隐藏提示
    if (!missingImage && !missingAV) { tip.hidden = true; return; }

    // 分别提示约定子目录：图片 → anchors/，音视频 → references/
    $$('.empty-folder-path').forEach((el) => {
      const sub = el.dataset.sub || '';
      el.textContent = `data_root/${rel}/${sub}`.replace(/\/$/, '');
    });

    const imgLine = $('#empty-folder-img');
    const avLine = $('#empty-folder-av');
    if (imgLine) imgLine.style.display = missingImage ? '' : 'none';
    if (avLine) avLine.style.display = missingAV ? '' : 'none';

    tip.hidden = false;
  } catch {
    // 目录不存在或列取失败时，不打扰用户
    tip.hidden = true;
  }
}

// 上传素材前，若未确定任务文件夹，禁用上传。
export function updateUploadState() {
  const hasDir = !!taskFolderRelative();
  const uploadBtn = $('#upload-btn');
  const uploadFile = $('#upload-file');
  if (uploadBtn) uploadBtn.disabled = !hasDir;
  if (uploadFile) uploadFile.disabled = !hasDir;
}

// 空目录提示里的「去上传」：滚动到上传素材区并高亮
export function scrollToUpload() {
  const row = $('.upload-row');
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    row.classList.add('flash');
    setTimeout(() => row.classList.remove('flash'), 1600);
  }
}

// 空目录提示里的「去现场生成」：切到现场生成说明区块并滚动到 Anchor 字段
export function goGenerateAnchor() {
  window.setAnchorSource?.('generate');
  const anchorLabel = [...document.querySelectorAll('.fields > label')].find((l) => l.textContent.includes('Anchor 文件'));
  if (anchorLabel) {
    anchorLabel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    anchorLabel.classList.add('flash');
    setTimeout(() => anchorLabel.classList.remove('flash'), 1600);
  }
}

// ── Preview Helpers ─────────────────────────────────────────────────────────

function previewPath(file) {
  const root = taskFolderRelative();
  const path = root ? `${root.replace(/\/$/, '')}/${file}` : file;
  return `/api/file-preview?root=data_root&path=${encodeURIComponent(path)}`;
}

export function renderAssetChips(field) {
  const container = $(`.asset-chips[data-field="${field}"]`);
  if (!container) return;
  // references 字段需根据当前 tab 区分视频(#references)还是音频(#audio-refs)
  const isAudioTab = field === 'references'
    && document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const sourceField = isAudioTab ? 'audio-refs' : field;
  const files = lines(`#${sourceField}`);
  if (!files.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = files.map((file) => {
    const name = file.split('/').pop();
    return `<span class="asset-chip" title="${escapeHtml(file)}">${escapeHtml(name)}<button type="button" class="chip-remove" data-type="${field}" data-file="${escapeAttr(file)}" title="取消选中">✕</button></span>`;
  }).join('');
}

export function renderVideoAssetPreviews() {
  renderAssetChips('anchors');
  renderAssetChips('references');
  const anchorFiles = lines('#anchors');
  // 根据当前 ref-tab 决定读视频字段还是音频字段
  const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const referenceFiles = isAudioTab ? lines('#audio-refs') : lines('#references');

  const anchorEl = $('#anchor-file-previews');
  if (anchorEl) {
    anchorEl.innerHTML = anchorFiles.length
      ? anchorFiles.map((file) => `<figure class="asset-figure" data-file="${escapeAttr(file)}"><img src="${previewPath(file)}" loading="eager" onerror="this.onerror=null;this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22%3E✗%3C/text%3E%3C/svg%3E'"><button type="button" class="asset-remove" data-type="anchors" data-file="${escapeAttr(file)}" title="取消选中">✕</button><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`).join('')
      : '<p class="hint">未选择任何文件</p>';
  }

  const refEl = $('#reference-file-previews');
  if (refEl) {
    refEl.innerHTML = referenceFiles.length
      ? referenceFiles.map((file) => {
          const isAudio = /\.(mp3|wav|m4a|aac|flac|ogg)$/i.test(file);
          const media = isAudio
            ? `<div class="asset-audio-icon">♪</div>`
            : `<video src="${previewPath(file)}#t=0.1" preload="metadata" muted onerror="console.error('Failed to load:',this.src)"></video>`;
          return `<figure class="asset-figure${isAudio ? ' asset-audio' : ''}" data-file="${escapeAttr(file)}">${media}<button type="button" class="asset-remove" data-type="references" data-file="${escapeAttr(file)}" title="取消选中">✕</button><figcaption>${escapeHtml(file.split('/').pop())}</figcaption></figure>`;
        }).join('')
      : '<p class="hint">未选择任何文件</p>';
  }
}

export function removeVideoAsset(type, file) {
  let target = type === 'anchors' ? '#anchors' : '#references';
  // references 在音频 tab 下操作 #audio-refs
  if (type === 'references') {
    const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
    if (isAudioTab) target = '#audio-refs';
  }
  const el = $(target);
  if (!el) return;
  const current = el.value.split('\n').map((v) => v.trim()).filter(Boolean);
  el.value = current.filter((v) => v !== file).join('\n');
  renderVideoAssetPreviews();
}

// ── Asset Picker ────────────────────────────────────────────────────────────

export async function openAssetPicker(category) {
  store.assetPickerCategory = category;
  store.assetPickerRoot = taskFolderRelative();
  const root = store.assetPickerRoot.replace(/\/$/, '');
  // 分类决定默认目录（约定：图片 → anchors/，音视频 → references/）：
  // - Anchor 图片：上传与「设为 Anchor」的图都统一在 anchors/ 根目录，默认直接进去；
  // - 参考音视频：统一在 references/，不混图片、不混内部目录。
  // 若默认目录不存在，browseAssets 会自动逐级回退到任务根目录。
  store.assetPickerPath = `${root}/${category === 'anchors' ? 'anchors' : 'references'}`;
  // 已选中项：references 在音频 tab 下读 #audio-refs
  const isAudioTab = category === 'references'
    && document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  store.assetPickerSelected = new Set(lines(category === 'anchors' ? '#anchors' : (isAudioTab ? '#audio-refs' : '#references')));
  $('#asset-picker-title').textContent = category === 'anchors' ? '选择 Anchor 图片' : '选择参考音视频';
  $('#asset-picker-modal').hidden = false;
  await browseAssets(store.assetPickerPath);
}

export function closeAssetPicker() {
  $('#asset-picker-modal').hidden = true;
}

export async function browseAssets(path) {
  try {
    let data;
    // 逐级向上回退：默认子目录（anchors/、references/）不存在时，
    // 自动回退到父目录乃至任务根目录，让用户能看到直接放在根目录下的素材。
    let cur = path;
    while (true) {
      try {
        data = await api(`/api/files?root=data_root&path=${encodeURIComponent(cur)}`);
        break;
      } catch (e) {
        const parent = String(cur).split('/').slice(0, -1).join('/');
        if (parent && parent !== cur) {
          cur = parent;
        } else {
          throw e;
        }
      }
    }
    store.assetPickerPath = data.path === '.' ? '' : data.path;
    $('#asset-picker-path').textContent = `data_root/${store.assetPickerPath}`;

    const parent = store.assetPickerPath.split('/').slice(0, -1).join('/');
    const base = store.assetPickerRoot ? store.assetPickerRoot.replace(/\/$/, '') + '/' : '';
    const relative = (item) => (item.path.startsWith(base) ? item.path.slice(base.length) : item.path);
    const extRe = store.assetPickerCategory === 'references'
      ? /\.(mp4|mov|m4v|webm|mp3|wav|m4a|aac|flac|ogg)$/i
      : /\.(png|jpe?g|webp)$/i;
    const allowed = (item) => extRe.test(item.name);

    // 目录过滤：隐藏内部目录（seedance/ tasks/），并根据类别过滤无关目录。
    // 选音视频 → 隐藏 anchor 图片目录；选图片 → 隐藏音视频目录（references/ audio/ 等）。
    const INTERNAL_DIR = /^(seedance|tasks|\.|\.\.)$/i;
    const allowedDir = (item) => {
      if (INTERNAL_DIR.test(item.name)) return false;
      if (store.assetPickerCategory === 'references') {
        return !/^anchors?$|anchor/i.test(item.name);
      }
      return !/^(references?|audio|videos?)$/i.test(item.name);
    };

    const root = store.assetPickerRoot ? store.assetPickerRoot.replace(/\/$/, '') : '';
    // 当前目录下符合类别的文件数
    const currentFiles = data.items.filter((item) => !item.directory && allowed(item));
    // 若当前目录（默认子目录）没有可选文件，但任务主目录里有同类文件，引导用户去主目录找
    // 注意：root 目录（如 anchor-references/）可能不存在，请求失败时须跳过引导，否则会中断
    // 后续的列表渲染，导致上一次打开 picker 的旧文件残留显示。
    let rootHint = '';
    if (currentFiles.length === 0 && store.assetPickerPath && store.assetPickerPath !== root) {
      try {
        const rootData = await api(`/api/files?root=data_root&path=${encodeURIComponent(root)}`);
        const rootFiles = (rootData.items || []).filter((item) => !item.directory && allowed(item));
        if (rootFiles.length > 0) {
          const label = store.assetPickerCategory === 'anchors' ? '图片' : '音视频';
          rootHint = `<button class="asset-root-hint" onclick="browseAssets('${escapeAttr(root)}')"><span>💡 当前目录没有可选${label}，主目录里有 ${rootFiles.length} 个</span><span>去主目录 ›</span></button>`;
        }
      } catch {
        // root 目录不存在，跳过主目录引导，继续渲染当前目录列表
      }
    }

    // 现场生成候选引导：只要存在 generated/ 目录就提示，方便用户同时看到「现场生成的候选」和「自己上传的图」。
    let generatedHint = '';
    if (store.assetPickerCategory === 'anchors') {
      const generatedDir = data.items.find((item) => item.directory && item.name === 'generated');
      if (generatedDir) {
        const hint = currentFiles.length === 0
          ? '🎬 现场生成的候选在 generated/ 里（尚未设为 Anchor）'
          : '💡 generated/ 里还有现场生成的候选，需要的话也可进入选取';
        generatedHint = `<button class="asset-generated-hint" onclick="browseAssets('${escapeAttr(generatedDir.path)}')"><span>${hint}</span><span>进入 ›</span></button>`;
      } else if (/\/generated(\/|$)/.test(store.assetPickerPath)) {
        generatedHint = `<div class="asset-generated-tip">这些是现场生成的候选。若要固定到正式目录（anchors/ 根目录），请在 Anchor 审核页「设为 Anchor」。</div>`;
      }
    }

    const list = $('#asset-picker-list');
    const visibleItems = data.items.filter((item) => (item.directory ? allowedDir(item) : allowed(item)));
    const hasVisibleDirs = data.items.some((item) => item.directory && allowedDir(item));
    list.innerHTML =
      (store.assetPickerPath
        ? `<button onclick="browseAssets('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>`
        : '') +
      rootHint +
      generatedHint +
      data.items
        .map((item) =>
          item.directory
            ? (allowedDir(item)
                ? `<button onclick="browseAssets('${escapeAttr(item.path)}')"><span>${escapeHtml(item.name)}</span><span>›</span></button>`
                : '')
            : allowed(item)
              ? `<label class="file-option">${(store.assetPickerCategory === 'anchors' || store.assetPickerCategory === 'anchor-references') ? `<img class="file-thumb" src="/api/file-preview?root=data_root&path=${encodeURIComponent(item.path)}" loading="lazy" onerror="this.style.display='none'" alt="">` : ''}<span>${escapeHtml(item.name)}</span><input type="checkbox" value="${escapeHtml(relative(item))}" ${store.assetPickerSelected.has(relative(item)) ? 'checked' : ''} onchange="toggleAsset(this)"></label>`
              : ''
        )
        .join('') +
      // 空状态提示：当前目录（及其可见子目录）都没有可选文件
      (visibleItems.length === 0 && !hasVisibleDirs
        ? (store.assetPickerCategory === 'anchor-references'
            ? `<div class="asset-empty-tip">📂 当前目录还没有参考图。<br>可以用「本机上传」从本机上传，或手动把图片放到：<br><code>data/${escapeHtml(store.assetPickerRoot || store.assetPickerPath || '<任务文件夹>/anchors/anchor-references')}</code></div>`
            : `<div class="asset-empty-tip">📂 当前目录没有可选素材。</div>`)
        : '');
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
        // 参考图 file 需相对 anchors/ 子目录（与上传、后端 _reference_source 解析一致）。
        // picker 的 assetPickerRoot 指向 .../anchors/anchor-references/，relative 截断后只剩
        // 纯文件名（如 IMG.jpg），需补回 anchor-references/ 前缀；含 / 的完整路径保持原样。
        const refFile = store.assetPickerCategory === 'anchor-references' && !file.includes('/')
          ? `anchor-references/${file}`
          : file;
        store.anchorReferences.push({
          id: `ref-${store.anchorReferences.length + 1}`,
          file: refFile,
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

  let target = store.assetPickerCategory === 'anchors' ? '#anchors' : '#references';
  // 参考音视频：根据选中文件类型自动判断 tab —— 全音频则切音频 tab，
  // 含视频则切视频 tab（视频 tab 为主输入）。
  if (store.assetPickerCategory === 'references') {
    const selected = [...store.assetPickerSelected];
    const hasVideo = selected.some((f) => /\.(mp4|mov|m4v|webm|avi|mkv)$/i.test(f));
    if (hasVideo) {
      switchRefTab('video');
      target = '#references';
    } else {
      switchRefTab('audio');
      target = '#audio-refs';
    }
  }
  $(target).value = [...store.assetPickerSelected].join('\n');
  renderVideoAssetPreviews();
  closeAssetPicker();
}

// ── Folder Picker ───────────────────────────────────────────────────────────

export function openFolderPicker() {
  store.folderPath = '';
  store.folderPickerTarget = null;  // 任务文件夹选择器（区别于现场生成的 anchor 目录选择器）
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
    $('#folder-path').textContent = `data_root/${store.folderPath}`;
    const parent = store.folderPath.split('/').slice(0, -1).join('/');
    // 只在顶层（data_root 根）对一级任务文件夹提供「删除文件夹」入口
    const isRoot = !store.folderPath;
    $('#folder-list').innerHTML =
      `<div class="folder-new">
        <input id="new-folder-name" type="text" placeholder="新建文件夹名称...">
        <button class="primary" onclick="createFolder()">新建</button>
      </div>` +
      (store.folderPath ? `<button onclick="browseFolder('${escapeAttr(parent)}')"><span>上一级</span><span>..</span></button>` : '') +
      data.items
        .filter((i) => i.directory)
        .map((i) => `<div class="folder-row">
          <button class="folder-row-main" onclick="browseFolder('${escapeAttr(i.path)}')"><span>${escapeHtml(i.name)}</span><span>›</span></button>
          ${isRoot ? `<button class="folder-row-del" onclick="confirmDeleteDataDir('${escapeAttr(i.name)}')" title="删除此任务文件夹及其所有任务与生成产物">🗑</button>` : ''}
        </div>`)
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

export async function confirmDeleteDataDir(dataDir) {
  // 先取关联信息，用于强确认弹窗明确列出级联删除的全部内容
  let usage;
  try {
    usage = await api(`/api/data-dirs/${encodeURIComponent(dataDir)}`);
  } catch (e) {
    toast(`获取目录信息失败: ${e.message}`);
    return;
  }

  const tasks = usage.tasks || [];
  const anchor = usage.anchor_task;
  const runTotal = (usage.video_runs || 0) + (usage.anchor_runs || 0);

  // 构造级联树：目录 → 各类资源 → 关联运行/产物
  const row = (children, label, detail) => `<div class="cascade-row"><span class="cascade-line">${children}</span><span class="cascade-label">${label}</span>${detail ? `<span class="cascade-detail">${detail}</span>` : ''}</div>`;

  let body = '';
  body += `<div class="cascade-root">📁 <strong>${escapeHtml(dataDir)}</strong></div>`;

  // 视频任务（每个任务单独一行，标注关联运行数）
  tasks.forEach((t, i) => {
    const isLast = i === tasks.length - 1 && !anchor;
    const detail = t.run_count > 0 ? `${t.run_count} 次运行 · 生成产物` : '无运行';
    body += row(isLast ? '└─' : '├─', `视频任务「${escapeHtml(t.name)}」`, detail);
  });

  // Anchor 任务
  if (anchor) {
    const detail = anchor.run_count > 0 ? `${anchor.run_count} 次运行 · 候选图` : '无运行';
    body += row('└─', `Anchor 任务「${escapeHtml(anchor.name)}」`, detail);
  }

  // 素材与缓存
  const refDetail = (usage.ref_count || 0) > 0 ? `${usage.ref_count} 个文件` : '空';
  body += row('├─', '参考音视频（references/）', refDetail);
  body += row('├─', 'Anchor 图片与候选（anchors/）', anchor ? '随 Anchor 任务删除' : '（无 Anchor 任务）');
  body += row(usage.has_seedance ? '└─' : '└─', 'Seedance 素材缓存', usage.has_seedance ? '存在' : '无');

  const totalTasks = tasks.length + (anchor ? 1 : 0);
  const summary = `<div class="cascade-summary">共 ${totalTasks} 个任务 · ${runTotal} 条运行记录 · 删除后不可恢复</div>`;

  const htmlDesc = body + summary;

  const ok = await window.showDeleteConfirm({
    title: '删除整个任务文件夹',
    htmlDesc,
    showFileOption: false,
    confirmText: '确认删除整个目录',
    danger: true,
  });
  if (!ok) return;

  try {
    await fetch(`/api/data-dirs/${encodeURIComponent(dataDir)}`, { method: 'DELETE' });
    toast(`已删除目录「${dataDir}」`);
    await browseFolder(store.folderPath);
    await loadTasks();
    await loadRuns();
  } catch (e) {
    toast(`删除失败: ${e.message}`);
  }
}

export async function chooseFolder() {
  const target = store.folderPickerTarget;
  const inputId = target === 'anchor' ? '#anchor-id' : '#task-dir';
  const newPath = store.folderPath || '';
  const oldPath = $(inputId).value.trim();

  // 切换任务文件夹时，若已填素材/歌词/约束，需清空并提醒确认
  if (inputId === '#task-dir' && newPath !== oldPath) {
    const hasSelected =
      lines('#anchors').length > 0 ||
      lines('#references').length > 0 ||
      lines('#audio-refs').length > 0 ||
      !!($('#lyrics')?.value.trim()) ||
      !!($('#constraints')?.value.trim());
    if (hasSelected) {
      const ok = await window.showDeleteConfirm({
        title: '切换任务文件夹',
        desc: `切换将清空已选的 Anchor 图片、参考音视频、歌词和附加约束。\n\n从「${oldPath || '(未设置)'}」切换到「${newPath || '(根目录)'}」`,
        showFileOption: false,
        confirmText: '确认切换',
        danger: false,
      });
      if (!ok) {
        store.folderPickerTarget = null;
        closeFolderPicker();
        return;  // 用户取消，保持原目录和已填内容不变
      }
    }
    // 清空上一个文件夹残留的素材、歌词和约束
    $('#anchors').value = '';
    $('#references').value = '';
    $('#audio-refs').value = '';
    if ($('#lyrics')) $('#lyrics').value = '';
    if ($('#constraints')) $('#constraints').value = '';
    renderVideoAssetPreviews();
  }

  // 切换 Anchor 任务文件夹时，清空上一个目录残留的参考图（与任务文件夹清空逻辑一致）
  let anchorMod = null;
  if (inputId === '#anchor-id' && newPath !== oldPath) {
    const hasRefs = store.anchorReferences.length > 0;
    if (hasRefs) {
      const ok = await window.showDeleteConfirm({
        title: '切换任务文件夹',
        desc: `切换将清空已选的参考图片。\n\n从「${oldPath || '(未设置)'}」切换到「${newPath || '(根目录)'}」`,
        showFileOption: false,
        confirmText: '确认切换',
        danger: false,
      });
      if (!ok) {
        store.folderPickerTarget = null;
        closeFolderPicker();
        return;  // 用户取消，保持原目录和已选参考图不变
      }
    }
    store.anchorReferences = [];
    store.currentAnchorTask = null;
    anchorMod = await import('./anchor.js');
    anchorMod.syncAspectSourceDropdowns();
    anchorMod.renderAnchorReferences();
  }

  $(inputId).value = newPath;
  store.folderPickerTarget = null;
  closeFolderPicker();
  // 选择的是任务文件夹时，检测目录内是否已有素材
  if (inputId === '#task-dir') checkTaskFolderEmpty();
  // 选择的是 Anchor 任务文件夹时，检查目录内是否已有参考图
  if (inputId === '#anchor-id') anchorMod?.checkAnchorRefDir?.();
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
      const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
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
    lyrics_timestamps: store.currentTask?.lyrics_timestamps || store.pendingLyricsTimestamps || [],
    // 高级视频设置（默认值与后端 VideoTaskAdapter 一致）
    resolution: $('#video-resolution')?.value || '720p',
    ratio: $('#video-ratio')?.value || '9:16',
    generate_audio: $('#video-generate-audio')?.checked ?? false,
    watermark: $('#video-watermark')?.checked ?? false,
    output_format: $('#video-output-format')?.value || 'mp4',
  };
}

export function switchRefTab(tab) {
  const audioTA = $('#audio-refs');
  const padRow = $('.pad-mode-row');
  const passAudioWrap = $('#pass-audio-wrap');
  const mode = $('[name=mode]:checked')?.value;
  // #references 与 #audio-refs 均为隐藏数据载体（不直接显示裸文本框），
  // 选中文件的展示统一走 chips / previews，随 tab 切换重渲染。
  if (audioTA) audioTA.hidden = true;
  if (tab === 'video') {
    if (padRow) padRow.style.display = '';
    // motion 模式不显示"传参考音频"
    if (passAudioWrap) passAudioWrap.style.display = mode === 'motion' ? 'none' : '';
  } else {
    // 音频 tab：隐藏时长对齐 + "传参考音频"（选音频 tab 就是要传音频）
    if (padRow) padRow.style.display = 'none';
    if (passAudioWrap) passAudioWrap.style.display = 'none';
  }
  $$('.ref-tab[data-ref-tab]').forEach(b => b.classList.toggle('active', b.dataset.refTab === tab));
  renderVideoAssetPreviews();
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
  let data;
  try {
    data = formTask();
  } catch (e) {
    toast(e.message);
    return null;
  }
  const newId = `${data.data_dir}__${data.name}`;
  const editingId = store.currentTask?.id;

  if (mode === 'auto') {
    if (editingId && editingId !== newId) {
      // 改了名字或文件夹：让用户选择新建还是更新
      showSaveModeDialog(data, editingId);
      return;
    }
    // 编辑同名任务（名字/文件夹未变）：视为更新
    if (editingId && editingId === newId) {
      mode = 'update';
    }
  }

  try {
    const task = await _doSave(data, editingId, mode);
    store.currentTask = task;
    toast('任务已保存');
    await loadTasks();
    return task;
  } catch (e) {
    toast(e.message);
    return null;
  }
}

async function _doSave(data, editingId, mode) {
  const newId = `${data.data_dir}__${data.name}`;
  // mode=update 且 id 变了（改名/改文件夹）：先删旧任务，再保存新任务
  if (mode === 'update' && editingId && editingId !== newId) {
    await api(`/api/tasks/${encodeURIComponent(editingId)}`, { method: 'DELETE' });
  }
  // 检查同名任务是否存在（同名更新除外）
  const existing = store.tasks?.find(t => t.id === newId);
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

const PAD_MODE_NAMES = { none: '原始时长', back: '后补齐', front: '前补齐' };

function _taskConfigChips(t) {
  const chips = [];
  chips.push(`<span class="cfg-chip cfg-mode">${modeName(t.mode)}</span>`);
  // 时长对齐（取第一个 reference 的 pad_mode，旧数据缺省 back）
  const pad = t.references?.[0]?.pad_mode || 'back';
  chips.push(`<span class="cfg-chip">⏱ ${PAD_MODE_NAMES[pad] || pad}</span>`);
  // 音视频传入
  const hasVideo = t.references?.some((r) => r.pass_reference_video !== false);
  const hasAudio = t.references?.some((r) => r.pass_reference_audio !== false);
  if (hasVideo && hasAudio) chips.push(`<span class="cfg-chip">🎬 视频+音频</span>`);
  else if (hasVideo) chips.push(`<span class="cfg-chip">🎬 仅视频</span>`);
  else if (hasAudio) chips.push(`<span class="cfg-chip">🎵 仅音频</span>`);
  // 歌词时间戳（打了几个有效时间点）
  const timedCount = (t.lyrics_timestamps || []).filter((x) => x?.time != null).length;
  if (timedCount > 0) chips.push(`<span class="cfg-chip cfg-ts">🎤 时间戳 ${timedCount} 句</span>`);
  // 候选数
  chips.push(`<span class="cfg-chip">${t.candidates} 候选</span>`);
  return chips.join('');
}

export async function loadTasks() {
  store.tasks = await api('/api/tasks');
  _renderTaskList();
}

function _renderTaskList() {
  const list = $('#task-list');
  if (!list) return;
  const sorted = [...store.tasks].sort((a, b) => {
    if (store.taskSort === 'name') {
      return (a.name || a.id).localeCompare(b.name || b.id, 'zh-Hans-CN');
    }
    // 时间排序：time-desc 最新在前，time-asc 最早在前（mtime 缺省按 0 兜底）
    return store.taskSort === 'time-asc'
      ? (a.mtime || 0) - (b.mtime || 0)
      : (b.mtime || 0) - (a.mtime || 0);
  });
  const html = sorted
    .map(
      (t) => `<article class="task" data-id="${escapeHtml(t.id)}">
        <div class="task-info">
          <h3>${escapeHtml(t.name || t.id)}</h3>
          <div class="meta">📁 ${escapeHtml(t.data_dir || t.task_dir || '?')} · ${t.anchors.length} anchors</div>
          <div class="cfg-chips">${_taskConfigChips(t)}</div>
        </div>
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

export function toggleTaskSort() {
  // 三态循环：时间降序 → 时间升序 → 名字
  const order = ['time-desc', 'time-asc', 'name'];
  store.taskSort = order[(order.indexOf(store.taskSort) + 1) % order.length];
  _updateSortButton('#task-sort-toggle', store.taskSort);
  _renderTaskList();
}

function _updateSortButton(selector, mode) {
  const btn = $(selector);
  if (!btn) return;
  const labels = { 'time-desc': '时间 ↓ 最新在前', 'time-asc': '时间 ↑ 最早在前', name: '名字 A-Z' };
  btn.textContent = labels[mode] || '排序';
  btn.title = '点击切换排序方式';
}

export function editTask(id) {
  const t = store.tasks.find((x) => x.id === id);
  if (!t) return;
  store.currentTask = t;
  const nameEl = $('#task-name');
  if (nameEl) nameEl.value = t.name || '';
  const dir = t.data_dir || t.task_dir || '';
  $('#task-dir').value = dir.endsWith('/') ? dir : dir;
  // 规范化路径：去掉可能存在的 data_dir 前缀（历史脏数据），保证相对 task_dir
  const stripDirPrefix = (file) => {
    const prefix = dir.replace(/\/+$/, '') + '/';
    return file && file.startsWith(prefix) ? file.slice(prefix.length) : file;
  };
  $('#candidates').value = t.candidates;
  $('#anchors').value = t.anchors.map((x) => stripDirPrefix(x.file)).join('\n');
  // 参考音视频：纯音频任务（pass_reference_video=false）写入音频字段，否则写入视频字段
  const isAudioOnly = t.references?.length > 0 && t.references.every(r => r.pass_reference_video === false);
  const refFiles = t.references.map((x) => stripDirPrefix(x.file));
  if (isAudioOnly) {
    $('#references').value = '';
    $('#audio-refs').value = refFiles.join('\n');
    switchRefTab('audio');
  } else {
    $('#references').value = refFiles.join('\n');
    $('#audio-refs').value = '';
    switchRefTab('video');
  }
  const passAudio = t.references[0]?.pass_reference_audio;
  const passAudioEl = document.getElementById('pass-reference-audio');
  if (passAudioEl) passAudioEl.checked = passAudio !== false;
  const passVideo = t.references[0]?.pass_reference_video;
  const passVideoEl = document.getElementById('pass-reference-video');
  if (passVideoEl) passVideoEl.checked = passVideo !== false;
  const padMode = t.references[0]?.pad_mode || 'none';
  switchPadMode(padMode);
  $('#lyrics').value = t.lyrics || '';
  if (!store.currentTask.lyrics_timestamps) store.currentTask.lyrics_timestamps = [];
  $('#constraints').value = t.constraints || '';

  // 回填高级视频设置（默认值与后端 VideoTaskAdapter 一致）
  const resEl = $('#video-resolution');
  if (resEl) resEl.value = t.resolution || '720p';
  const ratioEl = $('#video-ratio');
  if (ratioEl) ratioEl.value = t.ratio || '9:16';
  const genAudioEl = $('#video-generate-audio');
  if (genAudioEl) genAudioEl.checked = t.generate_audio === true;
  const wmEl = $('#video-watermark');
  if (wmEl) wmEl.checked = t.watermark === true;
  const fmtEl = $('#video-output-format');
  if (fmtEl) fmtEl.value = t.output_format || 'mp4';

  const radio = $(`[name=mode][value="${t.mode}"]`);
  if (radio) radio.checked = true;
  $$('.mode').forEach((m) => m.classList.toggle('active', m.contains(radio)));
  updateMode();
  renderVideoAssetPreviews();
  checkTaskFolderEmpty();
  checkMissingAssets(id);
  setTaskResetBtnLabel();
  // 编辑后滚动到「素材」区，让用户直接看到已选素材与现场生成候选提示
  const materialsPanel = $('#task-materials-panel');
  if (materialsPanel) materialsPanel.scrollIntoView({ block: 'start', behavior: 'auto' });
  else scrollTo({ top: 0, behavior: 'auto' });
}

// 检测任务引用的文件是否已被删除/不存在，给出明确提示
export async function checkMissingAssets(taskId) {
  const banner = $('#missing-assets-banner');
  if (!banner) return;
  if (!taskId) {
    banner.hidden = true;
    banner.innerHTML = '';
    return;
  }
  try {
    const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/missing-assets`);
    const missing = [...(result.missing_anchors || []), ...(result.missing_references || [])];
    if (!missing.length) {
      banner.hidden = true;
      banner.innerHTML = '';
      return;
    }
    const names = missing.map((m) => m.file.split('/').pop()).join('、');
    banner.hidden = false;
    banner.innerHTML = `⚠️ 以下文件已不存在：<strong>${escapeHtml(names)}</strong>。请在素材区移除或重新选择，否则保存/生成会失败。`;
    // 标记预览区对应文件
    markMissingPreviews(missing.map((m) => m.file));
  } catch (e) {
    banner.hidden = true;
  }
}

function markMissingPreviews(missingFiles) {
  const set = new Set(missingFiles);
  $$('.asset-figure').forEach((fig) => {
    const file = fig.dataset.file;
    if (file && set.has(file)) {
      fig.classList.add('missing');
      const cap = fig.querySelector('figcaption');
      if (cap) cap.textContent = cap.textContent.replace(/（文件已不存在）$/, '') + '（文件已不存在）';
    }
  });
}

export function resetForm() {
  $('#task-form').reset();
  // 显式清空素材字段（form.reset 对 hidden input 的清空在部分场景下不可靠）
  $('#anchors').value = '';
  $('#references').value = '';
  $('#audio-refs').value = '';
  store.currentTask = null;
  store.pendingLyricsTimestamps = null;
  $$('.mode').forEach((m, i) => m.classList.toggle('active', i === 0));
  updateMode();
  renderVideoAssetPreviews();
  checkMissingAssets('');
  checkTaskFolderEmpty();
  setTaskResetBtnLabel();
}

// 编辑态显示「取消」，非编辑态显示「新任务」
export function setTaskResetBtnLabel() {
  const btn = $('#task-reset-btn');
  if (btn) btn.textContent = store.currentTask ? '取消' : '新任务';
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
      <div class="asset-hint">素材通过<b>文件指纹</b>自动复用：源文件内容未变时<b>跳过上传</b>、直接复用已上传的 Seedance 资源，无需手动清理。仅在需要<b>强制重新上传</b>某个素材时才点 🗑 删除对应缓存。</div>
      <div class="asset-list">${data.items.length
        ? data.items
            .map((item) => {
              const srcName = item.source && item.source.path ? item.source.path.split('/').pop() : '';
              const type = item.key.startsWith('anchor_') ? 'Anchor 图片' : item.key.endsWith(':audio') ? '参考音频' : '参考视频';
              return `<div class="asset-row">
                <div><strong>${escapeHtml(item.key)}</strong><div class="meta">${escapeHtml(item.asset_id)}</div></div>
                <div class="meta">${escapeHtml(type)} · ${item.source ? `${escapeHtml(srcName || item.source.path)} · ${formatBytes(item.source.size)}` : '无源文件指纹'}</div>
                <button class="text-button danger-text" onclick="clearTaskAssets('${escapeAttr(id)}','${escapeAttr(item.key)}')" title="清除此素材缓存，下次运行会重新上传">🗑</button>
              </div>`;
            })
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
  const pre = $('#prompt-preview');
  const wrap = $('#prompt-preview-wrap');
  // 已展开 → 收起
  if (wrap && !wrap.hidden) {
    wrap.hidden = true;
    return;
  }
  try {
    const t = formTask();
    const result = await post('/api/prompt-preview', t);
    if (pre) pre.textContent = result.prompt;
    if (wrap) wrap.hidden = false;
    else if (pre) pre.hidden = false;
  } catch (e) {
    toast(e.message);
  }
}

export function closePromptPreview() {
  const wrap = $('#prompt-preview-wrap');
  if (wrap) wrap.hidden = true;
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
    const data = formTask();
    // 提交前校验：anchor 与参考音视频必填
    if (!data.anchors.length) throw new Error('请先选择或生成 Anchor 图片');
    if (!data.references.length) throw new Error('请先上传参考音视频');
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
  const statusEl = $('#upload-status');
  if (statusEl) statusEl.textContent = '上传中…';
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/uploads');
  xhr.timeout = 120000; // 2 分钟超时
  xhr.setRequestHeader('X-Task-Id', encodeURIComponent(id));
  xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
  xhr.setRequestHeader('X-Category', category);
  xhr.upload.onprogress = (e) => {
    if (statusEl && e.lengthComputable) statusEl.textContent = `${Math.round((e.loaded / e.total) * 100)}%`;
  };
  xhr.onload = () => {
    let errorMsg = null;
    if (xhr.status < 300) {
      // 后端返回的实际相对路径（例如 anchors/<filename>），优先使用，避免前后端路径不一致
      let uploadedFile = null;
      try { uploadedFile = JSON.parse(xhr.responseText).file; } catch { uploadedFile = null; }
      if (!uploadedFile) uploadedFile = `${category}/${file.name}`;
      // 根据当前 tab 决定写入视频字段还是音频字段
      const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
      const target = category === 'anchors' ? '#anchors' : (isAudioTab ? '#audio-refs' : '#references');
      const el = $(target);
      if (el) {
        el.value += `${el.value ? '\n' : ''}${uploadedFile}`;
      }
      if (statusEl) statusEl.textContent = '完成';
      renderVideoAssetPreviews();
      checkTaskFolderEmpty();
      toast('上传完成');
      // 清空文件选择框，便于连续上传；几秒后自动清空状态
      const fileInput = $('#upload-file');
      if (fileInput) fileInput.value = '';
      setTimeout(() => { if (statusEl && statusEl.textContent === '完成') statusEl.textContent = ''; }, 3000);
    } else {
      try { errorMsg = JSON.parse(xhr.responseText).error; } catch { errorMsg = `上传失败 (${xhr.status})`; }
      if (statusEl) statusEl.textContent = '';
      toast(errorMsg);
    }
  };
  xhr.onerror = () => {
    if (statusEl) statusEl.textContent = '';
    toast('上传失败：网络错误或服务未响应');
  };
  xhr.ontimeout = () => {
    if (statusEl) statusEl.textContent = '';
    toast('上传超时，请重试');
  };
  xhr.send(file);
}

// ── Runs ────────────────────────────────────────────────────────────────────

export async function loadRuns() {
  store.runs = await api('/api/runs');
  // 轮询场景（每 1.5s）下，数据未变化则跳过重渲染，避免整列表/审核下拉框反复重建导致的闪烁与选中态抖动
  const sig = JSON.stringify(store.runs.map((r) => [r.run_id, r.status, r.stage, r.completed, r.total, r.message]));
  if (sig === store._runsSig) return;
  store._runsSig = sig;
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

/* ── Rolling lyrics timestamps editor ── */
let _lyricsTsState = {
  lines: [],
  activeIndex: 0,
  audioUrl: null,
  extracting: false,
  scrollY: null,
};
let _lyricsAudioEl = null;
let _keyboardHelpShown = false;

function _formatTs(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function _parseLyricsText(text) {
  return text.split('\n').map((line) => line.trim()).filter((line) => line.length > 0);
}

export function showLyricsShortcuts() {
  toast('空格：播放/暂停  ·  Enter：添加时间点  ·  ↑/↓：切换歌词行  · Esc：关闭');
}

function _formReferenceFiles() {
  // 实时读取表单里的音视频引用：视频 tab 用 #references，音频 tab 用 #audio-refs
  const isAudioTab = document.querySelector('.ref-tab.active[data-ref-tab]')?.dataset?.refTab === 'audio';
  const files = isAudioTab ? lines('#audio-refs') : lines('#references');
  return { files, isAudioTab };
}

function _isMediaFile(name) {
  return /\.(mp3|wav|m4a|aac|flac|ogg|mp4|mov|m4v|avi|mkv|webm)$/i.test(name || '');
}

function _resolveAudioSource() {
  // 优先用表单当前的音视频引用（用户最新选择/切换的），表单为空时才回退到已保存任务
  const { files } = _formReferenceFiles();
  const formFile = files.find((f) => _isMediaFile(f));
  if (formFile) {
    return { source: 'form', index: 0, file: formFile };
  }
  const saved = store.currentTask?.references || [];
  const firstSaved = saved.find((r) => _isMediaFile(r.file));
  if (firstSaved) {
    return { source: 'task', index: saved.indexOf(firstSaved), file: firstSaved.file };
  }
  return null;
}

// 相对 data_root 的文件路径 = task_dir + '/' + 表单文件值（值已含 category 子目录）
function _relativeDataRootPath(file) {
  const taskDir = ($('#task-dir').value || '').trim().replace(/\/+$/, '');
  return taskDir ? `${taskDir}/${file}` : file;
}

function _applyLyricsText(texts, timestamps) {
  // texts 为新歌词行；timestamps 为已存时间戳（按 text 匹配保留 time）
  const timeByText = {};
  (timestamps || []).forEach((ts) => {
    if (ts?.text != null && ts.time != null) timeByText[ts.text] = ts.time;
  });
  _lyricsTsState.lines = texts.map((text) => ({
    text,
    time: timeByText[text] != null ? timeByText[text] : null,
  }));
  if (_lyricsTsState.activeIndex >= _lyricsTsState.lines.length) {
    _lyricsTsState.activeIndex = _lyricsTsState.lines.length - 1;
  }
}

export async function openLyricsTimestampsEditor() {
  const task = store.currentTask;
  const raw = $('#lyrics').value || '';
  const texts = _parseLyricsText(raw);

  // 音视频必须存在（歌词允许为空，未保存任务也允许）
  const ref = _resolveAudioSource();
  if (!ref) {
    return toast('请先上传音视频，再打时间戳');
  }

  const modal = $('#lyrics-timestamps-modal');
  _lyricsTsState.scrollY = window.scrollY;  // 记录滚动位置，关闭时恢复
  modal.hidden = false;
  if (!_keyboardHelpShown) {
    showLyricsShortcuts();
    _keyboardHelpShown = true;
  }

  const existing = task?.lyrics_timestamps || store.pendingLyricsTimestamps || [];
  _applyLyricsText(texts, existing);
  _lyricsTsState.activeIndex = 0;
  _lyricsTsState.audioUrl = null;
  _lyricsTsState.extracting = false;

  _lyricsAudioEl = $('#lyrics-audio');
  _lyricsAudioEl.src = '';
  _lyricsAudioEl.load();
  // 播放时自动滚动到当前时间对应的已打点句子
  _lyricsAudioEl.addEventListener('timeupdate', _autoLocateByTime);

  renderLyricsTimestampLines();
  _refreshAddButton();

  try {
    _lyricsTsState.extracting = true;
    $('#add-timestamp-btn').disabled = true;
    let res;
    if (ref.source === 'task') {
      res = await extractTaskAudio(task.id, ref.index);
    } else {
      res = await extractAudioByPath(_relativeDataRootPath(ref.file));
    }
    _lyricsTsState.audioUrl = res.audio_url;
    _lyricsAudioEl.src = res.audio_url;
    _lyricsAudioEl.load();
  } catch (e) {
    toast(`音频准备失败: ${e.message}`);
  } finally {
    _lyricsTsState.extracting = false;
    _refreshAddButton();
  }
}

function updateLyricsCountHint() {
  const hint = $('#lyrics-count-hint');
  if (!hint) return;
  const total = _lyricsTsState.lines.length;
  const set = _lyricsTsState.lines.filter((l) => l.time != null).length;
  hint.textContent = total ? `共 ${total} 句 · 已打点 ${set} 句` : '尚未填写歌词';
}

export function closeLyricsTimestampsEditor() {
  const modal = $('#lyrics-timestamps-modal');
  modal.hidden = true;
  if (_lyricsAudioEl) {
    _lyricsAudioEl.pause();
    _lyricsAudioEl.removeEventListener('timeupdate', _autoLocateByTime);
    _lyricsAudioEl.src = '';
    _lyricsAudioEl.load();
  }
  _lyricsTsState.audioUrl = null;
  // 恢复打开弹窗前的滚动位置（避免关闭后页面滚回顶部）
  if (typeof _lyricsTsState.scrollY === 'number') {
    requestAnimationFrame(() => window.scrollTo({ top: _lyricsTsState.scrollY, behavior: 'auto' }));
    _lyricsTsState.scrollY = null;
  }
}

function _refreshAddButton() {
  const btn = $('#add-timestamp-btn');
  if (!btn) return;
  btn.disabled = _lyricsTsState.extracting || !_lyricsAudioEl || !_lyricsAudioEl.src;
}

export function renderLyricsTimestampLines() {
  const container = $('#lyrics-timestamp-lines');
  if (!container) return;
  if (!_lyricsTsState.lines.length) {
    container.innerHTML = '<div class="lyrics-empty">歌词为空，请在上方逐行填写歌词后点击「应用歌词」</div>';
    return;
  }
  container.innerHTML = _lyricsTsState.lines.map((line, i) => {
    const tsClass = line.time != null ? 'set' : '';
    const activeClass = i === _lyricsTsState.activeIndex ? 'active' : '';
    const redoBtn = line.time != null
      ? `<button type="button" class="line-redo" data-index="${i}" title="重新打这一句">↺</button>`
      : '<span class="line-redo-placeholder"></span>';
    return `<div class="lyrics-line ${activeClass}" data-index="${i}">
      <div class="ts ${tsClass}">${_formatTs(line.time)}</div>
      <div class="text">${escapeHtml(line.text)}</div>
      ${redoBtn}
    </div>`;
  }).join('');
  container.querySelectorAll('.lyrics-line').forEach((el) => {
    el.addEventListener('click', () => clickLyricsLine(parseInt(el.dataset.index, 10)));
  });
  container.querySelectorAll('.line-redo').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation(); // 不触发行点击
      redoLyricsLine(parseInt(btn.dataset.index, 10));
    });
  });
  updateLyricsCountHint();
}

export function setActiveLine(index) {
  if (index < 0 || index >= _lyricsTsState.lines.length) return;
  _lyricsTsState.activeIndex = index;
  renderLyricsTimestampLines();
  _scrollActiveToSecondRow();
}

// 让当前打标句尽量滚动到第二行（第一句除外，它在顶部）
function _scrollActiveToSecondRow() {
  const container = $('#lyrics-timestamp-lines');
  if (!container) return;
  const active = container.querySelector('.lyrics-line.active');
  if (!active) return;
  const rows = container.querySelectorAll('.lyrics-line');
  const rowHeight = rows[0]?.offsetHeight || 0;
  const gap = 8;
  // 目标：active 行出现在第二行（即其上方只露出第一行）
  const targetTop = _lyricsTsState.activeIndex === 0
    ? 0
    : (_lyricsTsState.activeIndex - 1) * (rowHeight + gap);
  container.scrollTo({ top: targetTop, behavior: 'smooth' });
}

// 播放时根据当前时间自动定位到对应已打点句子
function _autoLocateByTime() {
  if (!_lyricsAudioEl || _lyricsAudioEl.paused) return;
  // 当前正在打点一个未打点的句子时，不自动回拉（尊重用户手动跳句）
  const currentLine = _lyricsTsState.lines[_lyricsTsState.activeIndex];
  if (currentLine && currentLine.time == null) return;
  const t = _lyricsAudioEl.currentTime;
  let target = -1;
  for (let i = 0; i < _lyricsTsState.lines.length; i++) {
    const time = _lyricsTsState.lines[i].time;
    if (time != null && time <= t) target = i;
    else if (time != null && time > t) break;
  }
  if (target >= 0 && target !== _lyricsTsState.activeIndex) {
    _lyricsTsState.activeIndex = target;
    renderLyricsTimestampLines();
    _scrollActiveToSecondRow();
  }
}

export function clickLyricsLine(index) {
  const line = _lyricsTsState.lines[index];
  if (!line) return;
  setActiveLine(index);
  // 已打点句子：点击跳转到对应时间点（仅定位，不清空）
  if (line.time != null && _lyricsAudioEl && _lyricsAudioEl.src) {
    _lyricsAudioEl.currentTime = line.time;
  }
}

export function redoLyricsLine(index) {
  const line = _lyricsTsState.lines[index];
  if (!line || line.time == null) return;
  // 清空这一句的时间点（只清这一句，不影响其它句）
  line.time = null;
  renderLyricsTimestampLines();

  // 选中定位到要重打的这一句
  setActiveLine(index);

  if (_lyricsAudioEl && _lyricsAudioEl.src) {
    if (index === 0) {
      // 第一句：从音频开头播放
      _lyricsAudioEl.currentTime = 0;
    } else {
      // 从上一句的时间点开始播放（留出准备缓冲），选中仍定位到要重打的这句
      const prev = _lyricsTsState.lines[index - 1];
      const startTime = prev && prev.time != null ? prev.time : Math.max(0, line.time - 2);
      _lyricsAudioEl.currentTime = startTime;
    }
  }
  toast(`从上一句开始播放，到「${line.text}」时按 Enter 重打`);
}

export function addTimestamp() {
  if (!_lyricsAudioEl || _lyricsTsState.extracting) return;
  if (!_lyricsTsState.lines.length) {
    toast('请先在任务表单中填写歌词');
    return;
  }
  const idx = _lyricsTsState.activeIndex;
  const time = _lyricsAudioEl.currentTime;
  const line = _lyricsTsState.lines[idx];
  if (!line) return;
  // 只覆盖当前句的时间点，不影响其它句子
  line.time = time;
  renderLyricsTimestampLines();
  if (_lyricsTsState.activeIndex < _lyricsTsState.lines.length - 1) {
    setActiveLine(_lyricsTsState.activeIndex + 1);
  }
  // 未播放时打点（如第一句 0s）后自动开始播放，方便连续打点
  if (_lyricsAudioEl.paused) {
    _lyricsAudioEl.play();
  }
}

export function resetTimestamps() {
  _lyricsTsState.lines.forEach((line) => { line.time = null; });
  _lyricsTsState.activeIndex = 0;
  renderLyricsTimestampLines();
}

export async function saveLyricsTimestampsFromModal() {
  const task = store.currentTask;
  const timestamps = _lyricsTsState.lines.map((line) => ({
    text: line.text,
    time: line.time,
  }));
  // 把 modal 里编辑的歌词同步回主表单
  const lyricsText = _lyricsTsState.lines.map((l) => l.text).join('\n');
  if ($('#lyrics')) $('#lyrics').value = lyricsText;
  // 任务尚未保存时，先暂存到内存，随任务保存时一并写入；否则直接持久化
  if (!task) {
    store.pendingLyricsTimestamps = timestamps;
    closeLyricsTimestampsEditor();
    toast('已暂存时间戳，保存任务后自动写入');
    return;
  }
  try {
    await saveLyricsTimestamps(task.id, timestamps);
    task.lyrics_timestamps = timestamps;
    closeLyricsTimestampsEditor();
    toast('歌词时间戳已保存');
  } catch (e) {
    toast(`保存失败: ${e.message}`);
  }
}

export function previewLyricsTimestamps() {
  const data = _lyricsTsState.lines.map((line) => ({
    text: line.text,
    time: line.time,
  }));
  console.log('[lyrics timestamps preview]', JSON.stringify(data, null, 2));
  toast(`已记录 ${_lyricsTsState.lines.filter((l) => l.time != null).length} 个时间点（按 F12 查看）`);
}

export function onLyricsTimestampsKey(e) {
  if ($('#lyrics-timestamps-modal').hidden) return;
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
  if (e.code === 'Space') {
    e.preventDefault();
    if (_lyricsAudioEl.paused) _lyricsAudioEl.play(); else _lyricsAudioEl.pause();
  } else if (e.code === 'Enter') {
    e.preventDefault();
    addTimestamp();
  } else if (e.code === 'ArrowUp') {
    e.preventDefault();
    setActiveLine(_lyricsTsState.activeIndex - 1);
  } else if (e.code === 'ArrowDown') {
    e.preventDefault();
    setActiveLine(_lyricsTsState.activeIndex + 1);
  }
  // Escape 关闭已统一由 app.js 的全局 modal 处理
}

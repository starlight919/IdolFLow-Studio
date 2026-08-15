// Centralized Application State
// ==========================================================================
//
// All shared data lives here. No globals on `window` except what the
// HTML onclick handlers need (exported via app.js).

const store = {
  // Workspace settings (data_root, publish_enabled)
  workspaceSettings: null,

  // ========== Video Tasks ==========
  tasks: [],
  runs: [],
  currentTask: null,
  pendingTask: null,
  pendingLyricsTimestamps: null,
  taskSort: 'time-desc',  // 'time-desc' | 'time-asc' | 'name-asc' | 'name-desc'
  customPromptDirty: false,  // 预览 Prompt 是否被用户手动编辑过（true=自定义）
  originalPadMode: null,  // 编辑任务时回填的原始 pad_mode，用于检测用户改动（null=新建）

  // ========== Asset Picker ==========
  assetPickerCategory: '',
  assetPickerPath: '',
  assetPickerRoot: '',
  assetPickerSelected: new Set(),
  folderPath: '',
  folderPickerTarget: null,  // 'anchor' | null（null = 任务文件夹选择器）

  // ========== Polling ==========
  pollTimer: null,
  anchorPollTimer: null,

  // ========== Anchor Tasks ==========
  anchorPresets: {},
  qualityPresets: {},
  negativePresets: {},
  anchorTasks: [],
  anchorRuns: [],
  anchorReferences: [],
  anchorManifest: null,
  anchorReviewState: null,
  pendingAnchorTask: null,
  anchorPickerMode: false,
  currentAnchorTask: null,
  anchorTaskSort: 'time-desc',  // 'time-desc' | 'time-asc' | 'name-asc' | 'name-desc'

  // ========== Review ==========
  reviewManifest: null,
  reviewState: null,
};

export default store;

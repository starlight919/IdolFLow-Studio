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
  runSort: 'time-desc',  // 运行记录的排序模式（与 taskSort 一致）
  customPromptDirty: false,  // 预览 Prompt 是否被用户手动编辑过（true=自定义）
  // 自由定制：参考图（customReferences）由素材弹窗维护；参考音视频（customRefs）由带标签的专属选择器维护
  customReferences: [],  // [{ file }] —— 参考图，复用打开素材入口
  customRefs: [],  // [{ file, kind:'video'|'audio', role }] —— 参考视频/音频，系统自动编号，用户只选语义标签
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
  anchorRunSort: 'time-desc',  // Anchor 运行记录的排序模式

  // ========== Review ==========
  reviewManifest: null,
  reviewState: null,
};

export default store;

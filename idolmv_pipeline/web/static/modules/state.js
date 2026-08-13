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

  // ========== Asset Picker ==========
  assetPickerCategory: '',
  assetPickerPath: '',
  assetPickerRoot: '',
  assetPickerSelected: new Set(),
  folderPath: '',

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

  // ========== Review ==========
  reviewManifest: null,
  reviewState: null,
};

export default store;

# 舞蹈 / 动作视频生成

> 最后更新：2026-08-12

动作任务通过 Web 工作台的「视频任务」面板创建，选择对应模式即可。

## 纯动作（motion）

Anchor 图片决定人物和画面，参考视频只提供舞蹈、手势和身体运动。不需要歌词。

任务配置：
```json
{
  "mode": "motion",
  "references": [
    {"name": "reference-1", "file": "dance.mp4", "duration": 15}
  ],
  "constraints": "动作自然流畅，保持人物身份、服装、发型和背景一致"
}
```

## 口型 + 动作（dance_lip_sync）

同时模仿唱歌口型和身体动作。歌词必须完整。

任务配置：
```json
{
  "mode": "dance_lip_sync",
  "references": [
    {
      "name": "reference-1",
      "file": "dance.mp4",
      "duration": 15,
      "pass_reference_audio": true
    }
  ],
  "lyrics": "完整歌词文本...",
  "constraints": "减小动作幅度"
}
```

## 生成流程

提交后自动完成：Prepare → Upload → Submit → Poll → Download → Mux → Manifest。

参见 [Video_Task_Workflow.md](Video_Task_Workflow.md) 获取完整流程说明。

## 优化提示

- 动作不完整 → 确认参考视频帧率稳定、动作清晰无遮挡
- 人物漂移 → 强化 `constraints` 中的身份保持约束
- 口型错位 → 确保歌词完整、参考视频中人脸清晰可见
- 动作幅度过大 → 在 `constraints` 中添加「减小动作幅度」

# 演唱 / 对口型视频指南

> 最后更新：2026-08-12

对口型任务使用 `lip_sync` 或 `dance_lip_sync` 模式。

## 必需输入

- 一张或多张 Anchor 图片（人物 + 场景）
- 一段口型参考视频
- 完整歌词文本

### 音频传入

对口型任务有参考视频时，视频可提取音频。默认勾选「上传参考音频做口型同步」，系统会将提取的音频上传给 Seedance 提升口型精度。可以取消（省一次上传），但最终 mux 阶段始终会用原始音频回灌到 `final.mp4`。

## 任务配置

```json
{
  "mode": "lip_sync",
  "references": [
    {
      "name": "reference-1",
      "file": "singing.mp4",
      "duration": 15,
      "pass_reference_audio": true
    }
  ],
  "lyrics": "完整歌词文本..."
}
```

## 时长

- Seedance 2.5 上限 30s，非 2.5 上限 15s
- 视频时长自动向上取整（17.857s → 18s），视频末尾补帧、音频末尾补静音到整数秒
- 生成后 mux 阶段用原始音频回灌，ffmpeg `-shortest` 自然裁回原始长度
- 详见 [Video_Task_Workflow.md](Video_Task_Workflow.md) 时长处理章节

## Prompt 原则

参见 [Prompt_Design.md](Prompt_Design.md) 获取五层架构详情。核心原则：

1. 图片 1 负责人物身份、服装、场景、光线
2. 视频 1 负责口型时序（lip_sync）或同时负责动作（dance_lip_sync）
3. 参考音频负责发音、音节、节奏和起止停顿
4. 口型多源融合：歌词（linguistic）+ 音频（acoustic+temporal）+ 视频（visual+temporal）
5. 保持嘴形自然、转换流畅，限制过度张嘴、机械抖动和五官漂移

## 常见问题

| 问题 | 排查 |
|------|------|
| 口型不准 | 确认歌词完整、参考人脸清晰、`pass_reference_audio` 已开启 |
| 搬运字幕或场景 | 系统 prompt 已限制「只取口型」，可加 `constraints` 强化 |
| 动作太大 | 使用 `lip_sync` 模式（纯对口型，不模仿动作） |
| 口型延迟 | 确认参考音频与视频对齐，加 `constraints` 强调时间同步 |

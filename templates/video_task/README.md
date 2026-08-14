# 视频任务模板

将本目录结构复制到 `data/<目录名>/`，素材分别放入 `anchors/` 和 `references/`，再把 `task.example.json` 改名为 `tasks/<任务名>.json`（同一目录可放多个任务），并填写内容。

Anchor 任务配置放在 `data/<目录名>/anchors/anchor-task.json`，生成的精选图会自动存入 `anchors/selected/` 供视频任务使用。

口型模式可增加 `lyrics.txt`（放在任务目录根，与 `tasks/` 同级），或直接在任务 JSON 的 `lyrics` 字段填写歌词。日常也可直接在 Web 工作台新建任务并上传素材。

# IdolFlow Studio 部署与运维

IdolFlow Studio 是 API-only 的 Anchor 与视频生成工作台。GPT Image 2 和 Seedance 均通过远程 API 调用；本机不需要 GPU、模型权重或本地模型工程。`ffmpeg`/`ffprobe` 用于参考视频处理和音频回灌。

## 系统要求

- Linux x86_64
- Python 3.10+
- `python3-venv`
- `ffmpeg`、`ffprobe`
- OpenSSH 客户端（Pinggy 素材隧道需要）
- 可访问配置的 API 服务

Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg openssh-client
```

## 首次部署

### 从私有 Git 仓库

```bash
git clone <private-repository> idolflow-studio
cd idolflow-studio
cp .env.example .env
# 编辑 .env
bash scripts/setup.sh
bash scripts/start.sh
```

### 从离线包

```bash
tar -xzf idolflow-studio.tar.gz
cd idolflow-studio
cp .env.example .env  # 如果交付包未携带 .env
bash scripts/setup.sh
bash scripts/start.sh
```

`.env` 必须通过受控渠道单独交付，不应提交到 Git。必填值：

```dotenv
SEEDANCE_API_BASE=https://<your-internal-gateway>/phanrouter
SEEDANCE_API_KEY=...
SEEDANCE_SD25_API_KEY=...
ASSET_GROUP_ID=...
VIDEO_SUBMIT_SECRET=<gen_password.py 生成>
VIDEO_SUBMIT_HASH=<gen_password.py 生成>
```

使用 Pinggy/Ngrok 时再填写相应 token。`setup.sh` 创建虚拟环境、安装 Python 依赖并创建运行目录；日常启动只需运行 `bash scripts/start.sh`。

### 提交密码机制（防误触/防外人）

提交生成需要输入密码，用于防止误触和"没有 `.env` 权限的人"乱点消耗 API 额度。

- **生成密钥**：`python3 scripts/gen_password.py <你的密码>`，把输出的 `VIDEO_SUBMIT_SECRET` 和 `VIDEO_SUBMIT_HASH` 写入 `.env`
- **`.env` 不存明文密码**，只存盐（SECRET）+ 哈希（HASH）；即使 `.env` 泄露也无法反推密码
- **两层授权**：要使用一个已部署实例，需要同时拿到 `.env`（部署权限）和原始密码（提交权限）
- **自建实例**：别人拿到代码后自己跑 `gen_password.py` 生成自己的密钥即可，消耗他自己的 API 额度，与你无关
- 生成算法公开（HMAC-SHA256）不影响安全，真正的秘密只有 `.env` 里的 SECRET/HASH

默认地址：`http://127.0.0.1:8913`。监听局域网：

```bash
bash scripts/start.sh --host 0.0.0.0 --port 8913
```

后台运行：

```bash
nohup bash scripts/start.sh --host 0.0.0.0 > workspace.log 2>&1 &
```

## 公网入口与素材隧道

保持工作台运行，在另一终端执行：

```bash
bash scripts/start-pinggy.sh
```

它暴露工作台网页。Seedance 提交时还会按需启动独立素材隧道，让远程 API 拉取 Anchor 和参考视频；两者用途和端口不同。

## 目录与持久化

```text
data/<数据目录>/
├── anchors/                  # Anchor 模块
│   ├── anchor-task.json
│   ├── anchor-references/
│   ├── generated/<run_id>/
│   └── selected/             # promote 的精选图
├── tasks/                    # Video 任务配置（支持同一目录多个任务）
│   ├── 唱歌版.json
│   └── 跳舞版.json
├── references/               # 参考音视频（视频 + 音频统一落点）
└── seedance/assets.json

runtime/work/<数据目录>/
runtime/outputs/<数据目录>/<run-id>/
```

任务、素材和 Anchor 审核结果位于 `data/`；视频中间文件与运行结果位于 `runtime/`。这些目录默认被 Git 忽略。

大容量部署可在 `video-workspace.json` 中使用绝对路径：

```json
{
  "data_root": "/srv/idolflow/data",
  "work_root": "/srv/idolflow/work",
  "output_root": "/srv/idolflow/outputs",
  "upload_root": "/srv/idolflow/data",
  "tunnel_root": "/srv/idolflow"
}
```

## 审核与发布

审核在主工作台的「审核」页完成：查看已生成的候选视频并下载。

`publish_enabled` 默认 `false`：关闭 Git 发布功能。

仅在具备目标 Git 仓库和可推送 remote 的工作机启用发布：

```json
{
  "publish_enabled": true,
  "publish_repo": "/srv/private/video-publish",
  "publish_subdirectory": "selected"
}
```

发布流程会逐个复制候选、仅暂存目标文件、创建 commit 并执行普通 `git push`。不要在普通部署中启用，也不要把工作机路径写进默认配置。

## CLI

```bash
python run.py anchor list --config video-workspace.json
python run.py anchor validate --task <id> --config video-workspace.json
python run.py anchor run --task <id> --config video-workspace.json
python run.py anchor status --task <id> --run-id <run-id> --config video-workspace.json

python run.py video list --config video-workspace.json
python run.py video validate --task <task-name> --config video-workspace.json
python run.py video run --task <task-name> --config video-workspace.json
```

日常任务创建、运行和审核建议使用网页。

## 更新与健康检查

更新源码后：

```bash
bash scripts/setup.sh
python -m compileall -q idolmv_pipeline run.py
node --check idolmv_pipeline/web/static/app.js
bash -n setup.sh start.sh start-pinggy.sh
bash scripts/start.sh --port 18913
```

另一个终端：

```bash
curl -f http://127.0.0.1:18913/api/settings/public
curl -f http://127.0.0.1:18913/api/anchor-presets
curl -f http://127.0.0.1:18913/api/tasks
curl -f http://127.0.0.1:18913/api/runs
```

## 备份与恢复

停服后备份 `data/`、`runtime/outputs/`、`video-workspace.json` 和通过安全渠道保存的 `.env`。恢复时部署同版本源码，将这些内容放回配置路径，执行 `bash scripts/setup.sh` 后启动。运行清单会从 `output_root` 自动发现。

## 排错

- **启动提示缺少 `.env`**：复制 `.env.example` 并填写必填值。
- **无法创建虚拟环境**：安装 `python3-venv`。
- **提交失败**：检查 API key、asset group、网络以及素材隧道 token。
- **视频处理失败**：运行 `ffmpeg -version` 和 `ffprobe -version`。
- **上传失败**：确认 `data_root`、`upload_root` 可写且任务路径未越界。
- **素材隧道失效**：服务会自动检测并重建，无需手动操作。若工作台网页隧道失效，重新运行 `bash scripts/start-pinggy.sh`。
- **发布失败**：确认发布已启用、目标是 Git 仓库、存在可推送 remote 且当前凭据有权限。

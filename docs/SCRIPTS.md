# 脚本使用指南

IdolFlow Studio 提供了一套简洁的脚本来管理服务。

## 📋 脚本列表

### 核心脚本

所有脚本位于项目根目录的 `scripts/` 下。

| 脚本 | 用途 | 使用频率 |
|------|------|----------|
| `scripts/setup.sh` | 安装依赖（首次使用） | 一次 |
| `scripts/start.sh` | 前台启动服务 | 常用 |
| `scripts/start-daemon.sh` | 后台启动服务 | 常用 |
| `scripts/stop.sh` | 停止服务 | 常用 |
| `scripts/status.sh` | 查看服务状态 | 常用 |
| `scripts/start-pinggy.sh` | 启动公网隧道 | 需要时 |

## 🚀 快速开始

### 首次使用

```bash
# 1. 安装依赖
bash scripts/setup.sh

# 2. 配置环境变量
cp .env.example .env
vi .env  # 填写必需的配置

# 3. 启动服务（选择一种方式）
bash scripts/start.sh          # 前台运行
# 或
bash scripts/start-daemon.sh   # 后台运行
```

### 日常使用

```bash
# 启动服务
bash scripts/start-daemon.sh

# 查看状态
bash scripts/status.sh

# 停止服务
bash scripts/stop.sh
```

## 📖 详细说明

### setup.sh - 安装依赖

**用途**: 首次使用时安装 Python 依赖和创建必要目录

**使用方法**:
```bash
bash scripts/setup.sh
```

**功能**:
- ✅ 检查 Python 版本 (需要 3.10+)
- ✅ 检查系统依赖 (ffmpeg, ffprobe, ssh)
- ✅ 安装 Python 依赖包
- ✅ 创建必要的目录结构
- ✅ 提示下一步操作

**输出示例**:
```
================================================
  IdolFlow Studio - 依赖安装
================================================

📌 检查 Python...
✅ Python 3.11.5

📌 检查系统依赖...
  ✅ ffmpeg
  ✅ ffprobe
  ✅ ssh

📦 安装 Python 依赖...
...

✅ 安装完成！
```

---

### start.sh - 前台启动

**用途**: 在当前终端前台运行服务

**使用方法**:
```bash
bash scripts/start.sh

# 自定义端口和主机
bash scripts/start.sh --host 0.0.0.0 --port 8080
```

**特点**:
- ✅ 日志直接显示在终端
- ✅ 按 `Ctrl+C` 停止
- ✅ 适合开发调试
- ❌ 关闭终端服务停止

**何时使用**:
- 开发测试时
- 需要实时查看日志
- 临时启动服务

---

### start-daemon.sh - 后台启动

**用途**: 后台持久化运行服务（推荐生产使用）

**使用方法**:
```bash
bash scripts/start-daemon.sh
```

**特点**:
- ✅ 后台运行，关闭终端也继续
- ✅ 日志保存到 `workspace.log`
- ✅ 进程 ID 保存到 `workspace.pid`
- ✅ 适合长期运行

**输出示例**:
```
🚀 启动 IdolFlow Studio (后台模式)...

✅ 服务已启动（后台运行）

📍 访问地址: http://127.0.0.1:8913/
📝 日志文件: workspace.log

常用命令:
  bash scripts/status.sh       # 查看状态
  bash scripts/stop.sh         # 停止服务
  tail -f workspace.log # 查看日志
```

**何时使用**:
- 生产环境部署
- 长期运行服务
- 服务器上运行

---

### stop.sh - 停止服务

**用途**: 停止正在运行的服务

**使用方法**:
```bash
bash scripts/stop.sh
```

**功能**:
- 自动查找运行中的服务进程
- 优雅停止服务
- 清理 PID 文件

**输出示例**:
```
🛑 停止 IdolFlow Studio...

✅ 服务已停止 (PID: 12345)
```

---

### status.sh - 查看状态

**用途**: 查看服务运行状态和信息

**使用方法**:
```bash
bash scripts/status.sh
```

**显示信息**:
- 服务是否运行
- 进程 ID
- CPU/内存使用
- 运行时长
- 最近日志
- 访问地址

**输出示例（运行中）**:
```
================================================
  IdolFlow Studio - 服务状态
================================================

✅ 状态: 运行中
🆔 进程 ID: 12345

📈 进程信息:
  PID  PPID  %CPU %MEM     ELAPSED COMMAND
12345     1   0.5  2.1    01:23:45 python3 run.py video web

📝 最近日志 (最后 5 行):
--------------------------------
Video workspace: http://127.0.0.1:8913/
--------------------------------

📍 访问地址: http://127.0.0.1:8913/

常用命令:
  bash scripts/stop.sh              # 停止服务
  tail -f workspace.log  # 实时查看日志

================================================
```

**输出示例（未运行）**:
```
================================================
  IdolFlow Studio - 服务状态
================================================

❌ 状态: 未运行

启动服务:
  bash scripts/start.sh             # 前台运行
  bash scripts/start-daemon.sh      # 后台运行

================================================
```

---

### start-pinggy.sh - 工作台网页公网隧道

> **素材隧道已自动集成**：上传素材给 Seedance 时服务会按需自动启动隧道，无需手动操作。此脚本仅用于把**工作台网页**暴露到公网（可选）。

**用途**: 将工作台网页（8913）暴露到公网，供外部浏览器访问 UI

**使用方法**:
```bash
bash scripts/start-pinggy.sh
```

**前提条件**:
- 服务已启动（运行 `bash scripts/start.sh` 或 `bash scripts/start-daemon.sh`）
- `.env` 中配置了 `PINGGY_TOKEN`

**功能**:
- 创建临时公网 HTTPS 地址
- 用于远程访问和素材隧道

**何时使用**:
- 需要从外网访问
- 提交任务时自动启动素材隧道
- 团队协作需要分享访问

## 🔄 常见工作流

### 场景 1: 本地开发测试

```bash
# 启动（前台，方便调试）
bash scripts/start.sh

# 在浏览器访问
open http://127.0.0.1:8913/

# 完成后停止（Ctrl+C）
```

### 场景 2: 服务器长期运行

```bash
# 启动后台服务
bash scripts/start-daemon.sh

# 检查状态
bash scripts/status.sh

# 查看日志
tail -f workspace.log

# 需要停止时
bash scripts/stop.sh
```

### 场景 3: 重启服务

```bash
# 停止
bash scripts/stop.sh

# 启动
bash scripts/start-daemon.sh

# 或者一条命令
bash scripts/stop.sh && bash scripts/start-daemon.sh
```

### 场景 4: 公网访问

```bash
# 1. 启动主服务
bash scripts/start-daemon.sh

# 2. 启动公网隧道（另一个终端）
bash scripts/start-pinggy.sh

# 会显示临时 URL，例如:
# https://xxxxx.free.pinggy.net
```

### 场景 5: 排查问题

```bash
# 1. 查看状态
bash scripts/status.sh

# 2. 查看完整日志
cat workspace.log

# 3. 实时监控日志
tail -f workspace.log

# 4. 前台运行看详细错误
bash scripts/stop.sh
bash scripts/start.sh  # 看终端输出
```

## ⚙️ 高级用法

### 自定义端口

```bash
# 前台运行在 8080 端口
bash scripts/start.sh --port 8080

# 后台运行监听所有网卡
bash scripts/start-daemon.sh --host 0.0.0.0 --port 8080
```

### 查看日志

```bash
# 查看最近 50 行日志
tail -n 50 workspace.log

# 实时查看日志
tail -f workspace.log

# 搜索错误
grep -i error workspace.log

# 清空日志
> workspace.log
```

### 系统服务（可选）

如需开机自动启动，可以配置 systemd（Linux）或 launchd（macOS）。

**macOS launchd 示例** (`~/Library/LaunchAgents/com.idolflow.studio.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.idolflow.studio</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/idol-video-studio/scripts/start-daemon.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/idol-video-studio</string>
</dict>
</plist>
```

加载服务:
```bash
launchctl load ~/Library/LaunchAgents/com.idolflow.studio.plist
```

## 🛠️ 故障排查

### 问题 1: 启动失败

**症状**: `bash scripts/start.sh` 或 `bash scripts/start-daemon.sh` 报错

**检查清单**:
```bash
# 1. 检查 .env 文件
cat .env | grep -v "^#" | grep -v "^$"

# 2. 检查依赖
bash scripts/setup.sh

# 3. 查看详细错误
bash scripts/start.sh  # 前台运行看详细输出
```

### 问题 2: 端口被占用

**症状**: `Address already in use`

**解决**:
```bash
# 查看占用端口的进程
lsof -i :8913

# 停止旧进程
bash scripts/stop.sh

# 或使用其他端口
bash scripts/start.sh --port 9000
```

### 问题 3: 服务自动停止

**检查日志**:
```bash
# 查看完整日志
cat workspace.log

# 查找错误
grep -i "error\|exception\|failed" workspace.log
```

### 问题 4: 无法访问

**检查清单**:
```bash
# 1. 服务是否运行
bash scripts/status.sh

# 2. 端口是否正确
lsof -i :8913

# 3. 防火墙设置
# macOS: 系统偏好设置 > 安全性与隐私 > 防火墙
# Linux: sudo ufw status
```

## 📝 脚本对比

| 特性 | start.sh | start-daemon.sh |
|------|----------|----------------|
| 运行方式 | 前台 | 后台 |
| 日志位置 | 终端 | workspace.log |
| 关闭终端 | 服务停止 | 继续运行 |
| 适用场景 | 开发调试 | 生产部署 |
| 停止方式 | Ctrl+C | bash scripts/stop.sh |

## 💡 最佳实践

1. **开发时使用 `bash scripts/start.sh`** - 方便看日志和调试
2. **生产时使用 `bash scripts/start-daemon.sh`** - 持久化运行
3. **定期查看 `bash scripts/status.sh`** - 监控服务状态
4. **定期清理日志** - 防止 `workspace.log` 过大
5. **更新代码后重启** - `bash scripts/stop.sh && bash scripts/start-daemon.sh`

## 🔗 相关文档

- [../README.md](../README.md) - 项目主页
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - 快速参考
- [DEPLOYMENT.md](DEPLOYMENT.md) - 部署指南

---

**最后更新**: 2026-08-11

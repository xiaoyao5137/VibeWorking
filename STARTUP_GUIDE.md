# 记忆面包 启动指南

## ✅ 系统状态

所有服务已成功启动并通过测试：

- ✅ Core Engine (Rust) - 运行在 http://localhost:7070
- ✅ AI Sidecar (Python) - 后台运行
- ✅ Desktop UI (Tauri + React) - 窗口应用已打开
- ✅ Vite 开发服务器 - 运行在 http://localhost:1420

## 🚀 启动方式

### 方式 1: 一键启动（推荐）

```bash
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz
./start.sh
```

这将按顺序启动所有服务：
1. AI Sidecar（后台）
2. Core Engine（后台）
3. Desktop UI（前台，会打开应用窗口）

### 方式 2: 手动分步启动

```bash
# 终端 1: AI Sidecar
cd ai-sidecar
source .venv/bin/activate
python main.py

# 终端 2: Core Engine
cd core-engine
cargo run --release

# 终端 3: Desktop UI
cd desktop-ui
npm run tauri:dev
```

## 📋 管理命令

```bash
./start.sh status      # 查看服务状态
./start.sh logs        # 查看实时日志
./start.sh stop        # 停止所有服务
./start.sh restart     # 重启所有服务
./test-system.sh       # 运行系统测试
```

## 🔧 API 端点

### Core Engine (http://localhost:7070)

- `GET /health` - 健康检查
- `GET /api/stats` - 获取统计数据
- `GET /api/vector/status` - 获取向量化状态

### 测试示例

```bash
# 健康检查
curl http://localhost:7070/health

# 查看统计
curl http://localhost:7070/api/stats

# 查看向量化状态
curl http://localhost:7070/api/vector/status
```

## 🐛 调试功能

在 Desktop UI 的设置页面，点击"🔧 打开调试面板"可以查看：
- 实时采集统计
- 向量化队列状态
- 数据库大小
- 最后采集时间

## 📝 日志位置

所有日志文件存储在：`~/.memory-bread/logs/`

- `sidecar.log` - AI Sidecar 日志
- `core.log` - Core Engine 日志

## ⚠️ 注意事项

1. 首次启动 Tauri 会编译 Rust 代码，需要等待几分钟
2. 确保端口 7070 和 1420 没有被占用
3. macOS 可能会提示安全警告，需要在"系统偏好设置 > 安全性与隐私"中允许运行

## 🎯 下一步

现在您可以：
1. 在 Desktop UI 中配置采集规则
2. 查看实时的采集和向量化状态
3. 通过 API 集成到其他应用

## 🔄 更新代码后

如果修改了代码，需要重新编译：

```bash
# Rust 代码
cd core-engine
cargo build --release

# React 代码（热重载，无需重启）
# Vite 会自动检测变化

# Tauri 配置
# 需要重启 npm run tauri:dev
```

---

**当前版本**: 0.1.0
**最后更新**: 2024-03-04

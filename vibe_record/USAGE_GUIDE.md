╔════════════════════════════════════════════════════════════╗
║           WorkBuddy 数据采集使用指南                      ║
╚════════════════════════════════════════════════════════════╝

## ✅ 系统状态

🎉 **数据采集功能已完全修复并正常工作！**

- ✅ Core Engine 运行中
- ✅ 采集引擎已启动
- ✅ 每 30 秒自动采集一次
- ✅ 截图正常保存
- ✅ 数据持续增长

## 📊 实时验证

```
测试时间线：
20:35:51 → 采集数: 5 (初始测试数据)
20:36:21 → 采集数: 7 (新增 2 条)
20:36:51 → 采集数: 8 (新增 1 条)
20:37:21 → 采集数: 10 (新增 2 条)
20:37:51 → 采集数: 11 (新增 1 条)

✅ 确认：每 30 秒增加新记录
```

## 🎯 如何查看采集数据

### 方法 1: 调试面板（推荐）

1. 打开 WorkBuddy 应用窗口
2. 点击左侧"设置"图标
3. 点击"🔧 打开调试面板"
4. 观察数据变化：
   - **系统统计**: 总采集数、向量化数、数据库大小
   - **最新记录**: 最近 20 条采集记录
   - **自动刷新**: 每 2 秒更新一次

### 方法 2: API 查询

```bash
# 查看统计
curl http://localhost:7070/api/stats

# 查看最新 5 条记录
curl 'http://localhost:7070/api/captures?limit=5'

# 查看向量化状态
curl http://localhost:7070/api/vector/status
```

### 方法 3: 数据库查询

```bash
# 查看总数
sqlite3 ~/.workbuddy/workbuddy.db "SELECT COUNT(*) FROM captures;"

# 查看最新 3 条
sqlite3 ~/.workbuddy/workbuddy.db "SELECT id, app_name, win_title, datetime(ts/1000, 'unixepoch', 'localtime') FROM captures ORDER BY ts DESC LIMIT 3;"

# 查看截图列表
ls -lht ~/.workbuddy/captures/screenshots/ | head -10
```

## 📸 采集的内容

每次采集会记录：

| 字段 | 说明 | 状态 |
|------|------|------|
| **时间戳** | 精确到毫秒 | ✅ 正常 |
| **应用名称** | 当前激活的应用 | ✅ 正常 |
| **窗口标题** | 当前窗口标题 | ✅ 正常 |
| **截图** | JPEG 格式，~1MB | ✅ 正常 |
| **事件类型** | auto (定时采集) | ✅ 正常 |
| AX 文本 | Accessibility 文本 | ⏳ 需要权限 |
| OCR 文本 | 图像文字识别 | ⏳ 需要 AI |
| 输入文本 | 键盘输入 | ⏳ 未实现 |

## ⚙️ 配置采集间隔

### 当前设置
- **间隔**: 30 秒
- **位置**: `core-engine/src/capture/listener.rs`

### 修改方法

**选项 1: 修改默认值**
```rust
// 编辑 core-engine/src/capture/listener.rs
impl Default for ListenerConfig {
    fn default() -> Self {
        Self {
            interval_secs: 60, // 改为 60 秒
        }
    }
}
```

**选项 2: 在 main.rs 中自定义**
```rust
// 编辑 core-engine/src/main.rs
let listener_config = ListenerConfig {
    interval_secs: 10, // 改为 10 秒（更频繁）
};
```

修改后需要重新编译：
```bash
cd core-engine
cargo build --release
pkill -f workbuddy
./target/release/workbuddy &
```

## 🔍 故障排查

### 如果数据不增长

1. **检查 Core Engine 是否运行**
   ```bash
   ps aux | grep workbuddy
   ```

2. **查看日志**
   ```bash
   tail -f /private/tmp/claude-501/-Users-xianjiaqi-Documents-mygit-cy-gzdz/tasks/blsi9wrfw.output
   ```
   应该看到：
   ```
   INFO 启动事件监听器，采集间隔: 30 秒
   DEBUG 触发定时采集事件
   INFO 采集完成: id=X, app=...
   ```

3. **检查数据库**
   ```bash
   sqlite3 ~/.workbuddy/workbuddy.db "SELECT COUNT(*) FROM captures;"
   ```

4. **重启服务**
   ```bash
   ./start.sh restart
   ```

### 如果截图失败

检查权限：
- macOS: 系统偏好设置 → 安全性与隐私 → 屏幕录制
- 确保 Terminal 或 workbuddy 有权限

### 如果 AX 文本为空

这是正常的，需要：
- macOS: 系统偏好设置 → 安全性与隐私 → 辅助功能
- 授予 workbuddy 辅助功能权限

## 📈 性能考虑

### 磁盘空间
- 每次采集约 1MB 截图
- 每小时约 120MB (30秒间隔)
- 每天约 2.9GB
- 建议定期清理旧数据

### 清理旧数据
```bash
# 删除 7 天前的截图
find ~/.workbuddy/captures/screenshots/ -name "*.jpg" -mtime +7 -delete

# 删除 30 天前的数据库记录
sqlite3 ~/.workbuddy/workbuddy.db "DELETE FROM captures WHERE ts < strftime('%s', 'now', '-30 days') * 1000;"
```

## 🎯 测试命令

```bash
# 快速测试脚本
./test-debug-panel.sh

# 完整系统测试
./test-system.sh

# 实时监控采集
watch -n 2 'curl -s http://localhost:7070/api/stats | python3 -m json.tool'
```

## 🚀 启动和停止

### 启动所有服务
```bash
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz
./start.sh
```

### 只启动 Core Engine
```bash
cd core-engine
./target/release/workbuddy &
```

### 停止服务
```bash
./start.sh stop
# 或
pkill -f workbuddy
```

### 重启服务
```bash
./start.sh restart
```

## 📝 日志位置

- **Core Engine**: `/private/tmp/claude-501/.../tasks/blsi9wrfw.output`
- **AI Sidecar**: `~/.workbuddy/logs/sidecar.log`
- **数据库**: `~/.workbuddy/workbuddy.db`
- **截图**: `~/.workbuddy/captures/screenshots/`

## 🎉 成功指标

✅ **采集数持续增长** - 每 30 秒 +1
✅ **截图文件生成** - 每次约 1MB
✅ **API 返回新数据** - 时间戳更新
✅ **调试面板显示** - 实时刷新
✅ **数据库记录增加** - SQL 查询验证

---

**当前状态**: ✅ 完全正常
**采集间隔**: 30 秒
**最后验证**: 2024-03-04 20:38
**采集记录**: 11+ 条（持续增长中）

🎊 现在您可以在调试面板中看到实时的数据采集了！

╔════════════════════════════════════════════════════════════╗
║           OCR 功能实现状态说明                            ║
╚════════════════════════════════════════════════════════════╝

## 📊 当前实现状态

### ✅ 已完成部分

1. **AI Sidecar OCR 引擎**
   - ✅ Apple Vision 后端实现（macOS）
   - ✅ PaddleOCR 后端实现（跨平台）
   - ✅ 自动平台检测和引擎选择
   - ✅ macOS 默认使用 Apple Vision
   - ✅ IPC 通信框架（Unix Socket）

2. **Core Engine 数据库**
   - ✅ `ocr_text` 字段定义
   - ✅ `update_ocr_text()` 方法实现
   - ✅ 截图保存功能
   - ✅ AX 文本采集

3. **配置验证**
   - ✅ Swift 可用（Apple Vision 依赖）
   - ✅ AI Sidecar 正常启动
   - ✅ Core Engine 正常运行

---

### ❌ 缺失部分（导致 OCR 文本为空）

**核心问题**: Core Engine 没有调用 AI Sidecar 执行 OCR

**技术方案要求**（第 77 行）：
```
截图 + Accessibility Tree 抓取
        │
写入 SQLite + 发送给 AI Sidecar
```

**当前实现**：
```
截图 + Accessibility Tree 抓取
        │
写入 SQLite ✅
        │
发送给 AI Sidecar ❌ (未实现)
```

---

## 🔧 需要实现的功能

### 方案 1: 同步 OCR（简单但阻塞）

**流程**：
```rust
// 在 CaptureEngine::process_event() 中
async fn process_event(&self, event: CaptureEvent) -> Result<Option<i64>> {
    // 1. 截图
    let screenshot_path = self.take_screenshot()?;

    // 2. AX 采集
    let ax_info = get_frontmost_info();

    // 3. 写入数据库
    let id = self.save_capture(ts, &ax_info, &event, screenshot_path, false)?;

    // 4. 如果 AX 文本为空，调用 OCR
    if ax_info.extracted_text.is_none() {
        let ocr_text = self.call_sidecar_ocr(&screenshot_path).await?;
        self.storage.update_ocr_text(id, &ocr_text, 0.95)?;
    }

    Ok(Some(id))
}
```

**优点**：
- 实现简单
- OCR 结果立即可用

**缺点**：
- ❌ 阻塞采集流程（OCR 需要 50-200ms）
- ❌ 影响采集性能
- ❌ 不符合技术方案的异步设计

---

### 方案 2: 异步 OCR（推荐）

**流程**：
```rust
// 在 CaptureEngine::process_event() 中
async fn process_event(&self, event: CaptureEvent) -> Result<Option<i64>> {
    // 1. 截图
    let screenshot_path = self.take_screenshot()?;

    // 2. AX 采集
    let ax_info = get_frontmost_info();

    // 3. 写入数据库
    let id = self.save_capture(ts, &ax_info, &event, screenshot_path, false)?;

    // 4. 如果 AX 文本为空，异步发送 OCR 任务
    if ax_info.extracted_text.is_none() {
        self.send_ocr_task(id, screenshot_path).await?;
    }

    Ok(Some(id))
}

// 后台任务处理 OCR 结果
async fn ocr_worker(&self) {
    while let Some((id, screenshot_path)) = self.ocr_queue.recv().await {
        match self.call_sidecar_ocr(&screenshot_path).await {
            Ok(ocr_text) => {
                self.storage.update_ocr_text(id, &ocr_text, 0.95)?;
            }
            Err(e) => {
                warn!("OCR 失败: {}", e);
            }
        }
    }
}
```

**优点**：
- ✅ 不阻塞采集流程
- ✅ 符合技术方案设计
- ✅ 可以批量处理

**缺点**：
- 实现稍复杂
- OCR 结果有延迟（但不影响采集）

---

## 🚀 快速验证方案（手动测试）

在实现自动 OCR 之前，可以先手动测试 OCR 功能：

### 步骤 1: 测试 AI Sidecar OCR

```bash
# 1. 找一张截图
SCREENSHOT=$(ls -t ~/.workbuddy/captures/screenshots/*.jpg | head -1)
echo "测试截图: $SCREENSHOT"

# 2. 创建测试脚本
cat > /tmp/test_ocr.py << 'EOF'
import sys
sys.path.insert(0, '/Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar')

from ocr.engine import OcrEngine

# 初始化引擎（macOS 会自动使用 Apple Vision）
engine = OcrEngine.create_default()

# 执行 OCR
screenshot_path = sys.argv[1]
result = engine.process(screenshot_path)

# 输出结果
print(f"识别到 {len(result.boxes)} 个文本框")
print(f"置信度: {result.confidence:.2f}")
print(f"\n完整文本:\n{result.text}")
EOF

# 3. 运行测试
python3 /tmp/test_ocr.py "$SCREENSHOT"
```

**预期输出**：
```
检测到 macOS，使用 Apple Vision 作为主 OCR 引擎
识别到 25 个文本框
置信度: 0.92

完整文本:
WorkBuddy
调试面板
最新采集记录
...
```

---

### 步骤 2: 手动更新数据库

```bash
# 1. 获取最新采集 ID
CAPTURE_ID=$(curl -s 'http://localhost:7070/api/captures?limit=1' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['captures'][0]['id'])
")

echo "最新采集 ID: $CAPTURE_ID"

# 2. 获取对应的截图
SCREENSHOT=$(curl -s "http://localhost:7070/api/captures/$CAPTURE_ID" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['screenshot_path'])
")

echo "截图路径: $SCREENSHOT"

# 3. 执行 OCR
OCR_TEXT=$(python3 /tmp/test_ocr.py ~/.workbuddy/captures/$SCREENSHOT | tail -n +4)

# 4. 手动更新数据库
sqlite3 ~/.workbuddy/workbuddy.db << EOF
UPDATE captures
SET ocr_text = '$OCR_TEXT'
WHERE id = $CAPTURE_ID;
EOF

echo "✅ OCR 文本已更新到数据库"

# 5. 验证
curl -s "http://localhost:7070/api/captures/$CAPTURE_ID" | python3 -m json.tool
```

---

## 📋 实现优先级

### 阶段 1: 手动验证（当前可做）

1. ✅ 测试 Apple Vision OCR 是否正常工作
2. ✅ 手动更新数据库验证流程
3. ✅ 在调试面板中查看 OCR 文本

**目标**: 验证 OCR 引擎配置正确

---

### 阶段 2: 实现异步 OCR（推荐）

1. 在 Core Engine 中添加 IPC 客户端
2. 实现 `call_sidecar_ocr()` 方法
3. 添加异步 OCR 任务队列
4. 实现后台 OCR worker

**目标**: 自动化 OCR 流程

---

### 阶段 3: 优化性能

1. 批量 OCR 处理
2. OCR 结果缓存
3. 智能降级（AX 成功时跳过 OCR）
4. 错误重试机制

**目标**: 生产环境优化

---

## 🎯 当前建议

**立即行动**: 先手动测试 OCR 功能，验证 Apple Vision 配置正确

```bash
# 快速测试
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar
python3 << 'EOF'
from ocr.engine import OcrEngine
import glob

# 获取最新截图
screenshots = sorted(glob.glob('/Users/xianjiaqi/.workbuddy/captures/screenshots/*.jpg'))
latest = screenshots[-1]

print(f"测试截图: {latest}")

# 初始化引擎
engine = OcrEngine.create_default()

# 执行 OCR
result = engine.process(latest)

print(f"\n✅ 识别成功!")
print(f"文本框数: {len(result.boxes)}")
print(f"置信度: {result.confidence:.2f}")
print(f"\n前 500 字符:\n{result.text[:500]}")
EOF
```

**下一步**: 如果测试成功，我可以帮你实现 Core Engine 的异步 OCR 调用

---

**更新时间**: 2026-03-05 00:45
**当前状态**: OCR 引擎已配置，等待集成到采集流程
**测试方法**: 手动测试脚本已提供

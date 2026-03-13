╔════════════════════════════════════════════════════════════╗
║           WorkBuddy 文本采集权限配置指南                  ║
╚════════════════════════════════════════════════════════════╝

## 📝 为什么文本字段是空的？

当前采集到的记录中，以下字段为空：
- ❌ **AX 文本** (ax_text) - 需要配置权限
- ❌ **OCR 文本** (ocr_text) - 需要启用 AI Sidecar
- ❌ **输入文本** (input_text) - 需要实现键盘监听
- ❌ **音频文本** (audio_text) - 需要实现音频采集

只有基本信息有值：
- ✅ **应用名称** (app_name)
- ✅ **窗口标题** (win_title)
- ✅ **采集时间** (ts)
- ✅ **截图路径** (screenshot_path)

## 🔧 各字段含义和配置方法

### 1. AX 文本 (Accessibility Text)

**含义**: 通过 macOS Accessibility API 获取的应用界面结构化文本

**当前状态**: ❌ 空（需要配置权限）

**配置方法**:

#### 方法 A: Chrome/Safari 浏览器（推荐）

**Chrome 用户**:
1. 打开 Google Chrome
2. 菜单栏 → **View** → **Developer** → **Allow JavaScript from Apple Events** ✓
3. 重启 WorkBuddy

**Safari 用户**:
1. 打开 Safari
2. 菜单栏 → **Safari** → **Preferences** → **Advanced**
3. 勾选 **Show Develop menu in menu bar** ✓
4. 菜单栏 → **Develop** → **Allow JavaScript from Apple Events** ✓
5. 重启 WorkBuddy

#### 方法 B: 系统辅助功能权限

1. 打开 **系统偏好设置**
2. **安全性与隐私** → **隐私** → **辅助功能**
3. 点击左下角 🔒 解锁
4. 添加以下应用：
   - `/Users/你的用户名/Documents/mygit/cy/gzdz/core-engine/target/release/workbuddy`
   - Terminal（如果从终端启动）
5. 勾选 ✓ 启用
6. 重启 WorkBuddy

**效果**:
- ✅ Chrome/Safari: 可以提取完整的网页文本内容（标题 + 正文）
- ✅ 其他应用: 可以提取部分 UI 元素文本

**限制**:
- 某些应用（如 Electron 应用）可能无法提取文本
- 需要用户手动授权

---

### 2. OCR 文本 (Optical Character Recognition)

**含义**: 从截图中识别出的文字内容

**当前状态**: ❌ 空（AI Sidecar 未启用 OCR）

**配置方法**:

#### 启用 AI Sidecar 的 OCR 功能

当前 AI Sidecar 运行在 dry-run 模式，不会真正调用 AI。要启用 OCR：

1. **配置 AI 服务**
   编辑 `ai-sidecar/config.yaml`:
   ```yaml
   ai:
     provider: openai  # 或 anthropic
     api_key: "your-api-key-here"
     model: "gpt-4o-mini"  # 或其他支持视觉的模型

   ocr:
     enabled: true
     quality: high
   ```

2. **重启 AI Sidecar**
   ```bash
   pkill -f ai-sidecar
   cd ai-sidecar
   python3 main.py
   ```

3. **验证 OCR 功能**
   ```bash
   curl -X POST http://localhost:8765/ocr \
     -H "Content-Type: application/json" \
     -d '{"image_path": "path/to/screenshot.jpg"}'
   ```

**效果**:
- ✅ 可以从任何应用的截图中提取文字
- ✅ 支持中英文混合识别
- ✅ 适用于所有应用（包括无法通过 AX 提取的）

**成本**:
- 需要 AI API 调用（每次约 $0.001-0.01）
- 每 30 秒采集一次，每天约 2880 次
- 预估成本：$3-30/天

**优化建议**:
- 增加采集间隔（60 秒或更长）
- 只对特定应用启用 OCR
- 使用本地 OCR 模型（如 Tesseract）

---

### 3. 输入文本 (Keyboard Input)

**含义**: 用户通过键盘输入的文本内容

**当前状态**: ❌ 空（功能未实现）

**实现方法**:

需要实现键盘事件监听器，监听用户的键盘输入。

**技术方案**:
- macOS: 使用 CGEventTap API
- 需要 Accessibility 权限
- 需要处理隐私和安全问题（密码框检测）

**隐私考虑**:
- ⚠️ 键盘监听涉及隐私敏感
- 需要检测密码框并跳过
- 需要用户明确授权

**当前状态**: 未实现（优先级较低）

---

### 4. 音频文本 (Audio Transcription)

**含义**: 从麦克风录音转换的文字内容

**当前状态**: ❌ 空（功能未实现）

**实现方法**:

需要实现音频采集和 ASR（自动语音识别）功能。

**技术方案**:
- 录音: macOS AVFoundation
- 转录: Whisper API 或本地 Whisper 模型
- 需要麦克风权限

**应用场景**:
- 会议记录
- 通话转录
- 语音备忘

**当前状态**: 未实现（未来功能）

---

## 🎯 推荐配置方案

### 方案 1: 最小配置（免费）

**只启用基本采集**:
- ✅ 应用名称
- ✅ 窗口标题
- ✅ 截图
- ❌ 不启用文本提取

**优点**: 无需配置，开箱即用
**缺点**: 无法搜索文本内容

---

### 方案 2: 浏览器文本提取（推荐）

**启用 Chrome/Safari 的 JavaScript 权限**:
- ✅ 应用名称
- ✅ 窗口标题
- ✅ 截图
- ✅ AX 文本（仅浏览器）

**配置步骤**:
1. Chrome: View → Developer → Allow JavaScript from Apple Events
2. 重启 WorkBuddy

**优点**: 免费，可以提取网页内容
**缺点**: 只对浏览器有效

---

### 方案 3: 完整 OCR（最强大）

**启用 AI Sidecar 的 OCR 功能**:
- ✅ 应用名称
- ✅ 窗口标题
- ✅ 截图
- ✅ OCR 文本（所有应用）

**配置步骤**:
1. 配置 AI API Key
2. 启用 OCR 功能
3. 重启 AI Sidecar

**优点**: 适用于所有应用，识别准确
**缺点**: 需要 AI API 成本

---

## 🧪 测试验证

### 测试 AX 文本提取

1. **打开 Chrome 浏览器**
2. **访问任意网页**（如 https://www.baidu.com）
3. **确保 Chrome 在前台**
4. **等待 30 秒**让系统采集
5. **打开调试面板**查看最新记录
6. **点击"查看详情"**

**预期结果**:
- 如果配置正确: AX 文本显示网页标题和内容
- 如果未配置: AX 文本为空

### 测试命令

```bash
# 查看最新采集记录
curl -s 'http://localhost:7070/api/captures?limit=1' | python3 -m json.tool

# 检查 AX 文本字段
curl -s 'http://localhost:7070/api/captures?limit=1' | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data['captures']:
    cap = data['captures'][0]
    print(f'应用: {cap[\"app_name\"]}')
    print(f'窗口: {cap[\"win_title\"]}')
    print(f'AX文本: {cap[\"ax_text\"][:100] if cap[\"ax_text\"] else \"(空)\"}')
    print(f'OCR文本: {cap[\"ocr_text\"][:100] if cap[\"ocr_text\"] else \"(空)\"}')
"
```

---

## 📊 当前系统状态

### 已实现功能
- ✅ 基本信息采集（应用名、窗口标题、时间）
- ✅ 截图保存
- ✅ AX 文本提取框架（需要权限配置）
- ✅ 数据库存储
- ✅ API 查询
- ✅ 调试面板显示

### 待配置功能
- ⏳ AX 文本提取（需要用户启用 Chrome JavaScript 权限）
- ⏳ OCR 文本识别（需要配置 AI API）

### 未实现功能
- ❌ 键盘输入监听
- ❌ 音频转录

---

## 🚀 快速开始

### 最简单的方式（推荐）

1. **打开 Chrome 浏览器**
2. **菜单栏** → View → Developer → **Allow JavaScript from Apple Events** ✓
3. **重启 WorkBuddy**:
   ```bash
   pkill -f workbuddy
   ./start.sh
   ```
4. **打开任意网页**（确保 Chrome 在前台）
5. **等待 30 秒**
6. **打开调试面板** → 点击最新记录的"查看详情"
7. **查看 AX 文本**应该显示网页内容

---

**更新时间**: 2024-03-04 21:05
**当前问题**: Chrome JavaScript 权限未启用
**解决方案**: View → Developer → Allow JavaScript from Apple Events

🎊 配置完成后，您就可以在调试面板中看到完整的网页文本内容了！

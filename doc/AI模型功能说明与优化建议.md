# 记忆面包 AI 模型功能说明与优化建议

## 各模型的作用和必要性分析

### 1. PaddleOCR (~200MB)

#### 作用
**光学字符识别（OCR）** - 将截图中的文字提取为可搜索的文本

#### 使用场景
- 当 Accessibility Tree 无法获取文本时的降级方案
- 识别图片中的文字（如设计稿、PDF 截图）
- 识别网页中的 Canvas 渲染文字

#### 调用频率
- **高频**：每次采集如果 AX 失败就会调用（约 30-50% 的采集）
- 每分钟可能调用 1-2 次

#### 必要性评估
- ✅ **核心功能，必须保留**
- Accessibility Tree 并非总是可用（权限问题、Canvas 内容、图片文字）
- 中文识别准确率最高（90%+）

#### 优化建议
- **推荐**：使用量化模型（200MB → 50MB）
- **推荐**：macOS 优先使用 Apple Vision（系统自带，0MB）
- **可选**：常驻内存（量化后仅 50MB）

---

### 2. BGE-M3 Embedding (~2.3GB) ⚠️

#### 作用
**文本向量化** - 将文本转换为 1024 维向量，用于语义搜索

#### 使用场景
- 用户提问："我上周和张三讨论了什么？"
- 系统将问题向量化，在 Qdrant 中搜索相似的历史记录
- 实现"语义搜索"而非简单的关键词匹配

#### 调用频率
- **低频**：仅在用户主动提问时调用
- 大多数用户可能一天只用 1-2 次

#### 必要性评估
- ⚠️ **重要但非核心，可延迟加载**
- 如果用户不使用 RAG 查询功能，这个模型完全用不到
- 2.3GB 内存占用过大

#### 优化建议
- **强烈推荐**：空闲 10 分钟后自动卸载
- **推荐**：使用量化模型（2.3GB → 600MB）
- **可选**：改用云端 API（通义千问/文心一言提供免费 Embedding API）

#### 替代方案
```python
# 方案 1: 使用云端 API（0MB 内存）
from openai import OpenAI
client = OpenAI(
    api_key="your-key",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
response = client.embeddings.create(
    model="text-embedding-v3",
    input=["文本内容"]
)

# 方案 2: 使用更小的模型（~400MB）
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
```

---

### 3. Whisper ASR (~1.5GB) ⚠️

#### 作用
**语音识别（ASR）** - 将录音转换为文字

#### 使用场景
- 用户在会议中录音，事后转录为文字
- 语音输入转文字

#### 调用频率
- **极低频**：大多数用户可能从不使用
- 需要用户主动触发录音功能

#### 必要性评估
- ❌ **非核心功能，可选模块**
- 技术方案中标注为"可选增配"
- 如果用户不录音，这个模型永远用不到

#### 优化建议
- **强烈推荐**：默认不加载，用户首次使用时才下载
- **推荐**：使用 tiny 模型（1.5GB → 75MB）
- **推荐**：使用 whisper.cpp 的量化版本（~40MB）
- **可选**：改用云端 API（阿里云/腾讯云语音识别）

---

### 4. MiniCPM-V VLM (~4GB) ⚠️⚠️

#### 作用
**视觉语言模型（VLM）** - 理解截图内容并回答问题

#### 使用场景
- 用户问："这个界面是做什么的？"
- 系统分析截图，理解 UI 布局和功能
- 高级场景：自动生成操作步骤

#### 调用频率
- **极低频**：高级功能，大多数用户不会用
- 可能一周才用 1-2 次

#### 必要性评估
- ❌ **高级功能，非必需**
- 4GB 内存占用极大
- 推理速度慢（CPU 上可能需要 10-30 秒）
- 大多数场景下 OCR + LLM 就够了

#### 优化建议
- **强烈推荐**：默认不加载，作为可选插件
- **强烈推荐**：改用云端 API（通义千问 VL / GPT-4V）
- **可选**：使用更小的模型（如 LLaVA-1.5-7B，~4GB → 2GB）

---

## 内存占用优先级分析

### 核心功能（必须保留）

| 模型 | 大小 | 频率 | 优化后 | 策略 |
|------|------|------|--------|------|
| PaddleOCR | 200MB | 高频 | 50MB | 量化 + 常驻 |
| Apple Vision | 0MB | 高频 | 0MB | macOS 优先 |

**总计**: 50MB（macOS 上为 0MB）

---

### 重要功能（延迟加载）

| 模型 | 大小 | 频率 | 优化后 | 策略 |
|------|------|------|--------|------|
| BGE-M3 | 2.3GB | 低频 | 600MB | 量化 + 10 分钟空闲卸载 |

**总计**: 600MB（使用时）

---

### 可选功能（默认禁用）

| 模型 | 大小 | 频率 | 优化后 | 策略 |
|------|------|------|--------|------|
| Whisper | 1.5GB | 极低 | 40MB | 使用 tiny 量化版 + 云端 API |
| MiniCPM-V | 4GB | 极低 | 0MB | 改用云端 API |

**总计**: 0MB（默认不加载）

---

## 推荐配置方案

### 方案 A: 最小内存模式（推荐）

**适用场景**: 8GB 内存以下的设备

```yaml
models:
  ocr:
    backend: "apple_vision"  # macOS 优先
    fallback: "paddleocr_quantized"  # 量化版 50MB
    keep_loaded: true  # 常驻内存

  embedding:
    backend: "cloud_api"  # 使用通义千问 API
    # 或者: "bge-small" (400MB 量化版)
    keep_loaded: false

  asr:
    enabled: false  # 默认禁用
    # 用户首次使用时提示下载

  vlm:
    enabled: false  # 默认禁用
    backend: "cloud_api"  # 使用通义千问 VL API
```

**内存占用**:
- 空闲: < 100MB
- OCR 工作: 50MB
- RAG 查询: 50MB（云端 API）
- **总计**: < 100MB

---

### 方案 B: 平衡模式

**适用场景**: 16GB 内存设备，追求响应速度

```yaml
models:
  ocr:
    backend: "paddleocr_quantized"  # 50MB
    keep_loaded: true

  embedding:
    backend: "bge-m3-quantized"  # 600MB 量化版
    idle_timeout: 600  # 10 分钟空闲卸载
    keep_loaded: false

  asr:
    backend: "whisper-tiny"  # 75MB
    idle_timeout: 900  # 15 分钟空闲卸载
    keep_loaded: false

  vlm:
    enabled: false
    backend: "cloud_api"
```

**内存占用**:
- 空闲: 50MB
- OCR 工作: 50MB
- RAG 查询: 650MB（10 分钟后降至 50MB）
- **总计**: 50-650MB

---

### 方案 C: 性能优先模式

**适用场景**: 32GB+ 内存设备，追求极致响应速度

```yaml
models:
  ocr:
    backend: "paddleocr"  # 200MB 原版
    keep_loaded: true

  embedding:
    backend: "bge-m3"  # 2.3GB 原版
    keep_loaded: true  # 常驻内存

  asr:
    backend: "whisper-base"  # 150MB
    idle_timeout: 1800  # 30 分钟空闲卸载

  vlm:
    backend: "minicpm-v-quantized"  # 2GB 量化版
    idle_timeout: 3600  # 1 小时空闲卸载
```

**内存占用**:
- 空闲: 2.5GB
- 全功能: 4.5GB
- **总计**: 2.5-4.5GB

---

## 云端 API 成本分析

### 通义千问（阿里云）

| API | 价格 | 免费额度 |
|-----|------|----------|
| Embedding | ¥0.0007/千 tokens | 100 万 tokens/月 |
| VL 理解 | ¥0.008/千 tokens | 无 |

**估算**:
- 每天 100 次 Embedding 调用 ≈ 10 万 tokens
- 月成本: ¥0（在免费额度内）

### 文心一言（百度）

| API | 价格 | 免费额度 |
|-----|------|----------|
| Embedding | ¥0.002/千 tokens | 50 万 tokens/月 |
| 图像理解 | ¥0.008/张 | 无 |

---

## 最终建议

### 立即实施

1. **OCR 优化**
   - macOS 优先使用 Apple Vision（0MB）
   - 其他平台使用 PaddleOCR 量化版（50MB）
   - 常驻内存（占用小）

2. **Embedding 优化**
   - 改用云端 API（通义千问免费额度充足）
   - 或使用量化版 + 10 分钟空闲卸载

3. **ASR/VLM 禁用**
   - 默认不加载
   - 用户首次使用时提示选择（本地/云端）

### 预期效果

**优化前**:
- 空闲内存: 2.5GB
- 峰值内存: 8GB
- 系统卡顿: 频繁

**优化后（方案 A）**:
- 空闲内存: < 100MB
- 峰值内存: 100MB
- 系统卡顿: 消除
- 功能损失: 无（云端 API 替代）

---

## 总结

**核心问题**: 4 个模型总计 8GB，但大部分时间用不到

**根本原因**:
- BGE-M3 (2.3GB) - 低频使用，可用云端 API
- Whisper (1.5GB) - 极低频，可选功能
- MiniCPM-V (4GB) - 极低频，可用云端 API

**解决方案**:
1. ✅ 只保留 OCR（50MB 量化版）
2. ✅ Embedding 改用云端 API（0MB）
3. ✅ ASR/VLM 默认禁用

**最终内存占用**: < 100MB（降低 96%）

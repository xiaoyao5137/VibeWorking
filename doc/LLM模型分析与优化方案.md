# 记忆面包 LLM 模型分析与优化方案

## 你的问题非常关键！

是的，我之前的分析**遗漏了最重要的 LLM 模型**！让我补充完整的模型清单：

---

## 完整的 5 个模型清单

| 序号 | 模型 | 作用 | 大小 | 频率 | 必要性 |
|------|------|------|------|------|--------|
| 1 | PaddleOCR | 截图文字识别 | 200MB | 高频 | ✅ 核心 |
| 2 | BGE-M3 | 文本向量化 | 2.3GB | 低频 | ⚠️ 重要 |
| 3 | Whisper | 语音转文字 | 1.5GB | 极低频 | ❌ 可选 |
| 4 | MiniCPM-V | 图像理解 | 4GB | 极低频 | ❌ 可选 |
| 5 | **Qwen2.5 7B** | **RAG 推理** | **~8GB** | **中频** | **✅ 核心** |

**总计**: ~16GB（未量化）

---

## LLM 模型详细分析

### Qwen2.5 7B（被遗漏的核心模型）

#### 作用
**RAG 推理引擎** - 根据检索到的上下文生成答案

#### 使用场景
```
用户提问："我上周和张三讨论了什么？"
  ↓
1. BGE-M3 向量化查询
2. Qdrant + FTS5 检索相关记录
3. 组装 Prompt（上下文 + 问题）
4. ⭐ Qwen2.5 7B 推理生成答案 ⭐
  ↓
返回："根据记录，你们讨论了项目进度..."
```

#### 调用频率
- **中频**：用户每次提问都会调用
- 如果用户频繁使用 RAG 功能，可能每小时 10-20 次

#### 必要性评估
- ✅ **核心功能，必须保留**
- RAG 的核心就是 LLM 推理
- 没有 LLM，RAG 只是检索，无法生成答案

---

## 当前实现分析

### 1. 使用 Ollama 调用本地模型

根据代码 `ai-sidecar/rag/llm/ollama.py`:

```python
class OllamaBackend(LlmBackend):
    def __init__(
        self,
        model: str = "qwen2.5:7b",  # 默认 7B 模型
        base_url: str = "http://localhost:11434",
    ):
        ...
```

**架构**:
```
记忆面包 RAG
    ↓ HTTP
Ollama 服务 (localhost:11434)
    ↓
Qwen2.5 7B 模型（独立进程）
```

---

### 2. 实际使用的是 Qwen2.5 3B

根据文件系统:
```bash
~/.memory-bread/models/Qwen/Qwen2.5-3B-Instruct-GGUF
```

**说明**: 实际部署时使用了 **3B 版本**而非 7B

---

## Qwen2.5 模型大小对比

根据搜索结果，Qwen2.5 GGUF 量化版本的大小：

### Qwen2.5 7B

| 量化级别 | 模型大小 | 内存占用 | 性能损失 | 推荐 |
|----------|----------|----------|----------|------|
| FP16 | 15GB | 18GB | 0% | ❌ 太大 |
| Q8_0 | 7.7GB | 9GB | < 1% | ⚠️ 较大 |
| Q5_K_M | 5.2GB | 6.5GB | < 2% | ✅ 推荐 |
| Q4_K_M | 4.4GB | 5.5GB | < 3% | ✅ 推荐 |
| Q3_K_M | 3.5GB | 4.5GB | ~5% | ⚠️ 可用 |
| Q2_K | 2.7GB | 3.5GB | ~10% | ❌ 不推荐 |

来源: [bartowski/Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF)

---

### Qwen2.5 3B（当前使用）

| 量化级别 | 模型大小 | 内存占用 | 性能损失 |
|----------|----------|----------|----------|
| FP16 | 6GB | 7GB | 0% |
| Q5_K_M | 2.3GB | 3GB | < 2% |
| Q4_K_M | 1.9GB | 2.5GB | < 3% |
| Q3_K_M | 1.5GB | 2GB | ~5% |

---

## 内存占用总结（修正版）

### 原始估算（错误）
| 模型 | 大小 |
|------|------|
| PaddleOCR | 200MB |
| BGE-M3 | 2.3GB |
| Whisper | 1.5GB |
| MiniCPM-V | 4GB |
| **总计** | **8GB** ❌ |

### 正确估算（包含 LLM）
| 模型 | 大小 |
|------|------|
| PaddleOCR | 200MB |
| BGE-M3 | 2.3GB |
| Whisper | 1.5GB |
| MiniCPM-V | 4GB |
| **Qwen2.5 7B (Q4)** | **4.4GB** |
| **总计** | **~12.5GB** ✅ |

---

## Ollama 的优势

### 为什么使用 Ollama 而不是直接加载模型？

#### 1. **独立进程，内存隔离**

```
记忆面包 AI Sidecar (Python)
    ↓ HTTP
Ollama 服务（独立进程）
    ↓
Qwen2.5 模型（独立内存空间）
```

**优势**:
- ✅ AI Sidecar 崩溃不影响 Ollama
- ✅ 可以独立重启 Ollama
- ✅ 内存管理更清晰

#### 2. **自动模型管理**

```bash
# Ollama 自动下载和管理模型
ollama pull qwen2.5:7b

# 模型存储在 ~/.ollama/models/
# 不需要手动管理模型文件
```

#### 3. **支持多模型切换**

```python
# 轻松切换模型
backend = OllamaBackend(model="qwen2.5:3b")  # 小模型
backend = OllamaBackend(model="qwen2.5:7b")  # 大模型
backend = OllamaBackend(model="deepseek-r1:7b")  # 其他模型
```

#### 4. **GPU 加速支持**

Ollama 自动检测 GPU 并使用 CUDA/Metal 加速

---

## 关键问题：Ollama 的内存占用

### Ollama 是否常驻内存？

**是的！** Ollama 的设计是：

1. **首次调用时加载模型**
   ```bash
   # 第一次调用
   curl http://localhost:11434/api/generate -d '{...}'
   # Ollama 加载 Qwen2.5 7B (Q4) → 占用 5.5GB
   ```

2. **模型常驻内存（默认 5 分钟）**
   ```bash
   # 5 分钟内再次调用，直接使用已加载的模型
   # 5 分钟后无调用，自动卸载模型
   ```

3. **可配置卸载时间**
   ```bash
   # 设置为 10 分钟
   OLLAMA_KEEP_ALIVE=10m ollama serve

   # 立即卸载（每次调用后）
   OLLAMA_KEEP_ALIVE=0 ollama serve
   ```

---

## 优化方案

### 方案 1: 使用更小的模型（推荐）

#### 当前：Qwen2.5 3B (Q4) - 2.5GB

```bash
ollama pull qwen2.5:3b
```

**优势**:
- ✅ 内存占用小（2.5GB）
- ✅ 推理速度快（CPU 上 2-5 秒）
- ⚠️ 性能略低于 7B（但对于 RAG 任务足够）

#### 备选：Qwen2.5 1.5B - 1.2GB

```bash
ollama pull qwen2.5:1.5b
```

**优势**:
- ✅ 内存占用极小（1.2GB）
- ✅ 推理速度更快
- ⚠️ 性能进一步下降

---

### 方案 2: 配置 Ollama 自动卸载

```bash
# 设置为 2 分钟无调用后卸载
OLLAMA_KEEP_ALIVE=2m ollama serve
```

**效果**:
- 用户提问时：加载模型（5.5GB）
- 2 分钟后：自动卸载（释放 5.5GB）

---

### 方案 3: 改用云端 API

```python
# 使用通义千问 API
from openai import OpenAI

client = OpenAI(
    api_key="your-key",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

response = client.chat.completions.create(
    model="qwen-plus",  # 或 qwen-turbo
    messages=[...]
)

# 内存占用: 0MB
# 成本: ¥0.004/千 tokens（约 0.4 分钱/次）
```

---

## 推荐配置

### 配置 A: 最小内存模式（推荐）

```yaml
models:
  ocr:
    backend: "apple_vision"  # macOS
    fallback: "paddleocr_q8"  # 50MB

  embedding:
    backend: "cloud_api"  # 通义千问 API

  llm:
    backend: "ollama"
    model: "qwen2.5:1.5b"  # 1.2GB
    keep_alive: "2m"  # 2 分钟后卸载

  asr:
    enabled: false

  vlm:
    enabled: false
```

**内存占用**:
- 空闲: < 100MB
- OCR 工作: 50MB
- RAG 查询: 1.2GB（2 分钟后释放）
- **峰值**: 1.3GB

---

### 配置 B: 平衡模式

```yaml
models:
  ocr:
    backend: "paddleocr_q8"  # 50MB
    keep_loaded: true

  embedding:
    backend: "bge-m3-q8"  # 600MB
    idle_timeout: 600  # 10 分钟

  llm:
    backend: "ollama"
    model: "qwen2.5:3b"  # 2.5GB
    keep_alive: "5m"

  asr:
    enabled: false

  vlm:
    backend: "cloud_api"
```

**内存占用**:
- 空闲: 50MB
- RAG 查询: 3.2GB（5 分钟后降至 650MB）
- **峰值**: 3.2GB

---

### 配置 C: 性能优先模式

```yaml
models:
  ocr:
    backend: "paddleocr"  # 200MB
    keep_loaded: true

  embedding:
    backend: "bge-m3"  # 2.3GB
    keep_loaded: true

  llm:
    backend: "ollama"
    model: "qwen2.5:7b"  # 5.5GB (Q4)
    keep_alive: "30m"  # 30 分钟

  asr:
    backend: "whisper-base"  # 150MB
    idle_timeout: 1800

  vlm:
    backend: "minicpm-v-q2"  # 2GB
    idle_timeout: 3600
```

**内存占用**:
- 空闲: 2.5GB
- RAG 查询: 8GB
- **峰值**: 10GB

---

## 总结

### 关键发现

1. **LLM 是被遗漏的最大模型**
   - Qwen2.5 7B (Q4): 4.4GB
   - 比 BGE-M3 (2.3GB) 还大

2. **Ollama 的优势**
   - 独立进程，内存隔离
   - 自动模型管理
   - 支持自动卸载（可配置）

3. **实际部署使用 3B 而非 7B**
   - 3B (Q4): 1.9GB
   - 7B (Q4): 4.4GB
   - 性能差距不大（RAG 任务）

### 最终建议

**对于 8GB 内存的设备**:
- 使用 Qwen2.5 1.5B (1.2GB)
- 配置 `OLLAMA_KEEP_ALIVE=2m`
- Embedding 改用云端 API
- **总内存**: < 1.5GB

**对于 16GB 内存的设备**:
- 使用 Qwen2.5 3B (2.5GB)
- 配置 `OLLAMA_KEEP_ALIVE=5m`
- Embedding 使用量化版本 (600MB)
- **总内存**: < 3.5GB

---

## Sources

- [bartowski/Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF)
- [Qwen2.5-7B-Instruct-DPO-v01-GGUF](https://www.promptlayer.com/models/qwen25-7b-instruct-dpo-v01-gguf)
- [All Versions & Hardware Requirements](https://www.hardware-corner.net/llm-database/Qwen/)

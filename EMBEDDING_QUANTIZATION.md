# Embedding 模型量化方案

## 当前问题

- **model_api_server 内存占用**：4.7GB（物理内存 3903M + 压缩内存 845M）
- **模型**：BAAI/bge-m3（1024 维，560M 参数）
- **设备**：CPU（MPS 不支持 sentence-transformers）

## 推荐方案：迁移到 Ollama Embedding API

### 方案 A：使用 Ollama 内置 embedding（推荐）

**优势**：
1. **统一进程**：复用 Ollama 进程，无需独立 model_api_server
2. **自动量化**：Ollama 自动使用量化模型（Q4/Q8）
3. **内存共享**：与 LLM 推理共享内存池
4. **零配置**：无需手动下载/管理模型

**模型选择**：

| 模型 | 维度 | 大小 | 内存占用 | 性能 | 推荐 |
|------|------|------|---------|------|------|
| [qllama/bge-small-zh-v1.5:q8_0](https://ollama.com/qllama/bge-small-zh-v1.5) | 512 | 95MB | ~200MB | 中文优化 | ⭐⭐⭐ |
| [qllama/bge-small-zh-v1.5:q4_k_m](https://ollama.com/qllama/bge-small-zh-v1.5) | 512 | 50MB | ~100MB | 中文优化 | ⭐⭐⭐⭐⭐ |
| nomic-embed-text:latest | 768 | 274MB | ~500MB | 英文优化 | ⭐⭐ |
| mxbai-embed-large:latest | 1024 | 669MB | ~1.2GB | 高精度 | ⭐ |

**推荐**：`qllama/bge-small-zh-v1.5:q4_k_m`（50MB，内存占用 ~100MB，中文优化）

**实现步骤**：

1. **安装模型**：
```bash
ollama pull qllama/bge-small-zh-v1.5:q4_k_m
```

2. **修改 embedding 后端**（ai-sidecar/embedding/ollama.py）：
```python
import requests

class OllamaEmbeddingBackend(EmbeddingBackend):
    def __init__(self, model_name: str = "qllama/bge-small-zh-v1.5:q4_k_m"):
        self._model_name = model_name
        self._api_url = "http://localhost:11434/api/embed"
    
    def is_available(self) -> bool:
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=1)
            return resp.status_code == 200
        except:
            return False
    
    def encode(self, texts: list[str]) -> list[EmbeddingVector]:
        resp = requests.post(self._api_url, json={
            "model": self._model_name,
            "input": texts
        })
        resp.raise_for_status()
        embeddings = resp.json()["embeddings"]
        return [
            EmbeddingVector(text=t, vector=e)
            for t, e in zip(texts, embeddings)
        ]
    
    @property
    def dimension(self) -> int:
        return 512  # bge-small-zh-v1.5
```

3. **更新 model.py**：
```python
from .ollama import OllamaEmbeddingBackend

class EmbeddingModel:
    def __init__(self, backend: EmbeddingBackend | None = None):
        self._backend = backend or OllamaEmbeddingBackend()
```

4. **移除 model_api_server**：
```bash
# 不再需要独立进程
# pkill -f model_api_server.py
```

**预期效果**：
- 内存占用：4.7GB → **100MB**（减少 97.9%）
- 启动速度：10 秒 → **< 1 秒**
- 维护成本：**大幅降低**

---

### 方案 B：使用 ONNX 量化模型（备选）

**适用场景**：不想依赖 Ollama，或需要离线部署

**模型选择**：

| 模型 | 大小 | 内存占用 | 来源 |
|------|------|---------|------|
| [gpahal/bge-m3-onnx-int8](https://huggingface.co/gpahal/bge-m3-onnx-int8) | 280MB | ~600MB | HuggingFace |
| [onnx-community/bge-small-zh-v1.5-ONNX](https://huggingface.co/onnx-community/bge-small-zh-v1.5-ONNX) | 95MB | ~200MB | HuggingFace |
| [CompendiumLabs/bge-small-zh-v1.5-gguf](https://huggingface.co/CompendiumLabs/bge-small-zh-v1.5-gguf) | 50MB | ~100MB | HuggingFace |

**实现步骤**：

1. **安装依赖**：
```bash
pip install optimum[onnxruntime]
```

2. **下载模型**：
```bash
cd ai-sidecar
huggingface-cli download onnx-community/bge-small-zh-v1.5-ONNX --local-dir ./models/bge-small-zh-v1.5-onnx
```

3. **修改后端**（ai-sidecar/embedding/onnx_backend.py）：
```python
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

class OnnxEmbeddingBackend(EmbeddingBackend):
    def __init__(self, model_path: str = "./models/bge-small-zh-v1.5-onnx"):
        self._model_path = model_path
        self._model = None
        self._tokenizer = None
    
    def _ensure_loaded(self):
        if self._model is None:
            self._model = ORTModelForFeatureExtraction.from_pretrained(self._model_path)
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
    
    def encode(self, texts: list[str]) -> list[EmbeddingVector]:
        self._ensure_loaded()
        inputs = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        outputs = self._model(**inputs)
        embeddings = outputs.last_hidden_state.mean(dim=1).detach().numpy()
        return [
            EmbeddingVector(text=t, vector=e.tolist())
            for t, e in zip(texts, embeddings)
        ]
```

**预期效果**：
- 内存占用：4.7GB → **200MB**（减少 95.7%）
- 推理速度：提升 30%（CPU 优化）

---

## 方案对比

| 维度 | 方案 A（Ollama） | 方案 B（ONNX） | 当前（PyTorch） |
|------|-----------------|---------------|----------------|
| 内存占用 | 100MB | 200MB | 4.7GB |
| 模型大小 | 50MB | 95MB | 560MB |
| 启动速度 | < 1s | ~3s | ~10s |
| 推理速度 | 快 | 快 | 中 |
| 维护成本 | 低 | 中 | 高 |
| 依赖 | Ollama | optimum | sentence-transformers |
| 离线部署 | ✅ | ✅ | ✅ |
| 推荐度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ |

---

## 实施计划

### 阶段 1：立即实施（方案 A）

1. **安装 Ollama embedding 模型**：
```bash
ollama pull qllama/bge-small-zh-v1.5:q4_k_m
```

2. **创建 Ollama 后端**：
```bash
# 创建文件
touch ai-sidecar/embedding/ollama.py
```

3. **修改默认后端**：
```python
# ai-sidecar/embedding/model.py
from .ollama import OllamaEmbeddingBackend

class EmbeddingModel:
    def __init__(self, backend: EmbeddingBackend | None = None):
        self._backend = backend or OllamaEmbeddingBackend()
```

4. **更新向量维度**：
```sql
-- shared/db-schema/migrations/xxx_update_vector_dimension.sql
-- 从 1024 → 512（如果需要重建索引）
```

5. **测试验证**：
```bash
# 测试 embedding API
curl -X POST http://localhost:11434/api/embed \
  -d '{"model":"qllama/bge-small-zh-v1.5:q4_k_m","input":["测试文本"]}'

# 启动 sidecar，观察内存
ps aux | grep python
```

6. **移除 model_api_server**（可选）：
```bash
# 确认 Ollama 方案稳定后
# 删除 model_api_server.py 相关代码
```

### 阶段 2：性能优化（1 周后）

1. **对比测试**：
   - 向量检索准确率（NDCG@10）
   - 推理速度（QPS）
   - 内存占用（峰值/平均）

2. **调优**：
   - 如果准确率下降 > 5%，考虑 q8_0 版本
   - 如果速度不满足，考虑批量优化

### 阶段 3：备选方案（按需）

如果 Ollama 方案不满足需求，切换到方案 B（ONNX）。

---

## 验证方法

### 1. 内存占用验证

```bash
# 修改前
ps aux | grep model_api_server
# 显示：3903M

# 修改后
ps aux | grep ollama
# 显示：~200M（包含 LLM + embedding）
```

### 2. 功能验证

```python
# 测试脚本
from embedding.model import EmbeddingModel

model = EmbeddingModel()
vectors = model.encode(["测试文本1", "测试文本2"])
print(f"维度: {len(vectors[0].vector)}")  # 应为 512
print(f"向量: {vectors[0].vector[:5]}")   # 应为浮点数列表
```

### 3. 性能验证

```bash
# 压力测试
time python -c "
from embedding.model import EmbeddingModel
model = EmbeddingModel()
for i in range(100):
    model.encode(['测试文本'] * 10)
"
```

预期：
- 修改前：~30 秒
- 修改后：~10 秒

---

## 回滚方案

如果 Ollama 方案出现问题，快速回滚：

```python
# ai-sidecar/embedding/model.py
from .bge import BgeM3Backend  # 恢复原后端

class EmbeddingModel:
    def __init__(self, backend: EmbeddingBackend | None = None):
        self._backend = backend or BgeM3Backend()  # 恢复
```

---

## 参考资料

- [Ollama Embedding API](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings)
- [qllama/bge-small-zh-v1.5](https://ollama.com/qllama/bge-small-zh-v1.5)
- [gpahal/bge-m3-onnx-int8](https://huggingface.co/gpahal/bge-m3-onnx-int8)
- [CompendiumLabs/bge-small-zh-v1.5-gguf](https://huggingface.co/CompendiumLabs/bge-small-zh-v1.5-gguf)
- [onnx-community/bge-small-zh-v1.5-ONNX](https://huggingface.co/onnx-community/bge-small-zh-v1.5-ONNX)

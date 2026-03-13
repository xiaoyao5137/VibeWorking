# WorkBuddy 知识提炼系统 V2 - 安装指南

## 📋 改进概述

### 核心改进
1. **强制使用 LLM 模型** - 不再使用低质量的规则提炼器
2. **知识去重机制** - 基于语义相似度（阈值 0.85）
3. **出现次数统计** - 新增 `occurrence_count` 字段
4. **更智能的重要性评分** - LLM 评估 1-5 分

### 去重工作流程
```
新采集记录
    ↓
LLM 提炼 → 生成摘要
    ↓
向量编码 → 获取向量
    ↓
查询现有知识 → 计算相似度
    ↓
相似度 >= 0.85?
    ├─ 是 → 更新 occurrence_count
    └─ 否 → 插入新记录
```

## 🚀 安装步骤

### 1. 安装 Ollama（正在进行中）
```bash
brew install ollama
```

### 2. 启动 Ollama 服务
```bash
# 后台启动
ollama serve &

# 或者在新终端窗口启动
ollama serve
```

### 3. 下载推理模型
```bash
# 下载 Qwen3.5-4B 模型（约 2.3GB）
ollama pull qwen3.5:4b
```

### 4. 验证安装
```bash
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar
source .venv/bin/activate
python startup_checks.py
```

应该看到所有检查通过：
```
✅ Ollama 已安装
✅ Ollama 服务运行中
✅ 推理模型已下载
✅ 向量模型已加载
```

### 5. 清空旧数据（可选）
```bash
# 删除低质量的知识条目
sqlite3 ~/.workbuddy/workbuddy.db << 'EOF'
DELETE FROM knowledge_entries;
EOF
```

### 6. 重启 AI Sidecar
```bash
# 停止旧进程
pkill -f "python.*main.py"

# 启动新进程
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar
source .venv/bin/activate
python main.py > ~/.workbuddy/logs/sidecar.log 2>&1 &
```

## 📊 数据库变更

### 新增字段
```sql
ALTER TABLE knowledge_entries
ADD COLUMN occurrence_count INTEGER DEFAULT 1;
```

### 字段说明
- `occurrence_count`: 知识出现次数，用于：
  - 识别高频知识点
  - 计算召回权重
  - 提升重要知识的排序

## 🎯 召回权重计算（未来实现）

```python
final_score = (
    semantic_similarity * 0.6 +      # 语义相似度 60%
    importance / 5 * 0.3 +            # 重要性评分 30%
    log(occurrence_count) / 10 * 0.1  # 出现次数 10%
)
```

## 📁 新增文件

### 1. `knowledge/extractor_v2.py`
- 新版知识提炼器
- 强制使用 LLM
- 支持语义去重
- 传递数据库连接

### 2. `startup_checks.py`
- 启动前置检查
- 验证 Ollama 安装
- 验证模型可用性

## 🔧 修改文件

### 1. `background_processor.py`
- 使用 `KnowledgeExtractorV2`
- 传递数据库连接用于去重
- 保存 `occurrence_count` 字段

### 2. `main.py`
- 启动前运行检查
- 检查失败则退出

## ⚠️ 注意事项

1. **Ollama 服务必须运行** - 否则 AI Sidecar 无法启动
2. **模型下载需要时间** - qwen3.5:4b 约 2.3GB
3. **首次处理较慢** - LLM 推理比规则提取慢，但质量高
4. **建议清空旧数据** - 旧的规则提取数据质量较差

## 📈 性能对比

### 规则提取器（旧）
- 速度：20 条/10 秒
- 质量：低（大量无意义内容）
- 去重：无

### LLM 提取器（新）
- 速度：约 5-10 条/10 秒（取决于硬件）
- 质量：高（智能过滤和摘要）
- 去重：有（语义相似度）

## 🐛 故障排查

### Ollama 服务无法启动
```bash
# 检查端口占用
lsof -i :11434

# 手动启动并查看日志
ollama serve
```

### 模型下载失败
```bash
# 检查网络连接
curl -I https://ollama.ai

# 重试下载
ollama pull qwen3.5:4b
```

### 启动检查失败
```bash
# 查看详细错误
cd /Users/xianjiaqi/Documents/mygit/cy/gzdz/ai-sidecar
source .venv/bin/activate
python startup_checks.py
```

## 📞 下一步

等待 Ollama 安装完成后：
1. 启动 Ollama 服务
2. 下载 qwen3.5:4b 模型
3. 运行启动检查
4. 重启 AI Sidecar
5. 观察日志确认正常工作

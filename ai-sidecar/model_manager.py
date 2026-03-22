"""
模型管理器 - 管理本地 AI 模型的下载、配置和切换

支持的模型类型：
1. 文本推理模型（LLM）- 用于知识提炼
2. 向量模型（Embedding）- 用于语义搜索
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """模型类型"""
    LLM = "llm"           # 文本推理模型
    EMBEDDING = "embedding"  # 向量模型


class ModelStatus(str, Enum):
    """模型状态"""
    NOT_INSTALLED = "not_installed"  # 未安装
    DOWNLOADING = "downloading"      # 下载中
    INSTALLED = "installed"          # 已安装
    ACTIVE = "active"                # 激活中


@dataclass
class ModelInfo:
    """模型信息"""
    id: str                    # 模型 ID
    name: str                  # 显示名称
    type: ModelType            # 模型类型
    provider: str              # 提供商（ollama/huggingface/openai）
    model_id: str              # 实际模型标识
    size_gb: float             # 模型大小（GB）
    description: str           # 描述
    status: ModelStatus = ModelStatus.NOT_INSTALLED
    is_default: bool = False   # 是否为默认模型
    requires_api_key: bool = False  # 是否需要 API Key


# 预定义的模型列表
AVAILABLE_MODELS = {
    # ========== 文本推理模型（LLM） ==========
    "qwen2.5-3b": ModelInfo(
        id="qwen2.5-3b",
        name="Qwen 2.5 (3B)",
        type=ModelType.LLM,
        provider="ollama",
        model_id="qwen2.5:3b",
        size_gb=2.0,
        description="阿里通义千问 2.5，3B 参数，轻量高效，适合本地运行",
        is_default=True
    ),
    "qwen3.5-4b": ModelInfo(
        id="qwen3.5-4b",
        name="Qwen 3.5 (4B)",
        type=ModelType.LLM,
        provider="ollama",
        model_id="qwen3.5:4b",
        size_gb=2.3,
        description="阿里通义千问 3.5，4B 参数，适合本地运行",
        is_default=False
    ),
    "qwen3.5-7b": ModelInfo(
        id="qwen3.5-7b",
        name="Qwen 3.5 (7B)",
        type=ModelType.LLM,
        provider="ollama",
        model_id="qwen3.5:7b",
        size_gb=4.1,
        description="阿里通义千问 3.5，7B 参数，更强的推理能力"
    ),
    "llama3.2-3b": ModelInfo(
        id="llama3.2-3b",
        name="Llama 3.2 (3B)",
        type=ModelType.LLM,
        provider="ollama",
        model_id="llama3.2:3b",
        size_gb=2.0,
        description="Meta Llama 3.2，3B 参数，轻量高效"
    ),
    "gemma2-2b": ModelInfo(
        id="gemma2-2b",
        name="Gemma 2 (2B)",
        type=ModelType.LLM,
        provider="ollama",
        model_id="gemma2:2b",
        size_gb=1.6,
        description="Google Gemma 2，2B 参数，最轻量"
    ),
    "openai-gpt4": ModelInfo(
        id="openai-gpt4",
        name="OpenAI GPT-4",
        type=ModelType.LLM,
        provider="openai",
        model_id="gpt-4",
        size_gb=0,
        description="OpenAI GPT-4，云端 API（需要 API Key）",
        requires_api_key=True
    ),

    # ========== 向量模型（Embedding） ==========
    "bge-m3": ModelInfo(
        id="bge-m3",
        name="BGE-M3",
        type=ModelType.EMBEDDING,
        provider="huggingface",
        model_id="BAAI/bge-m3",
        size_gb=2.2,
        description="BAAI BGE-M3，1024 维，支持中英文",
        is_default=True
    ),
    "bge-small": ModelInfo(
        id="bge-small",
        name="BGE-Small (中文)",
        type=ModelType.EMBEDDING,
        provider="huggingface",
        model_id="BAAI/bge-small-zh-v1.5",
        size_gb=0.1,
        description="BAAI BGE-Small，512 维，轻量中文模型"
    ),
    "text-embedding-3-small": ModelInfo(
        id="text-embedding-3-small",
        name="OpenAI Embedding (Small)",
        type=ModelType.EMBEDDING,
        provider="openai",
        model_id="text-embedding-3-small",
        size_gb=0,
        description="OpenAI 向量模型，云端 API（需要 API Key）",
        requires_api_key=True
    ),
}


class ModelManager:
    """模型管理器"""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path.home() / ".memory-bread" / "model_config.json"

        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """加载模型配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # 默认配置
        return {
            "active_llm": "qwen2.5-3b",
            "active_embedding": "bge-m3",
            "api_keys": {}
        }

    def _save_config(self):
        """保存模型配置"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def list_models(self, model_type: Optional[ModelType] = None) -> List[Dict]:
        """
        列出所有可用模型

        Args:
            model_type: 筛选模型类型，None 表示全部

        Returns:
            模型信息列表
        """
        models = []

        for model_id, model_info in AVAILABLE_MODELS.items():
            if model_type and model_info.type != model_type:
                continue

            # 检查模型状态
            status = self._check_model_status(model_info)
            model_dict = asdict(model_info)
            model_dict['status'] = status.value
            model_dict['type'] = model_info.type.value

            # 标记是否为当前激活的模型
            if model_info.type == ModelType.LLM:
                model_dict['is_active'] = (model_id == self.config.get('active_llm'))
            elif model_info.type == ModelType.EMBEDDING:
                model_dict['is_active'] = (model_id == self.config.get('active_embedding'))

            models.append(model_dict)

        return models

    def _check_model_status(self, model_info: ModelInfo) -> ModelStatus:
        """检查模型状态"""
        if model_info.provider == "ollama":
            return self._check_ollama_model(model_info.model_id)
        elif model_info.provider == "huggingface":
            return self._check_huggingface_model(model_info.model_id)
        elif model_info.provider == "openai":
            # API 模型不需要下载
            api_key = self.config.get('api_keys', {}).get('openai')
            return ModelStatus.INSTALLED if api_key else ModelStatus.NOT_INSTALLED

        return ModelStatus.NOT_INSTALLED

    def _check_ollama_model(self, model_id: str) -> ModelStatus:
        """检查 Ollama 模型是否已安装"""
        try:
            result = subprocess.run(
                ['ollama', 'list'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # 检查模型是否在列表中
                if model_id in result.stdout:
                    return ModelStatus.INSTALLED

            return ModelStatus.NOT_INSTALLED

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Ollama 未安装
            return ModelStatus.NOT_INSTALLED

    def _check_huggingface_model(self, model_id: str) -> ModelStatus:
        """检查 HuggingFace 模型是否已下载"""
        # 转换模型 ID 为缓存路径
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        model_dir = cache_dir / f"models--{model_id.replace('/', '--')}"

        if model_dir.exists():
            # 检查是否有 snapshots 目录且不为空
            snapshots_dir = model_dir / "snapshots"
            if snapshots_dir.exists() and list(snapshots_dir.iterdir()):
                return ModelStatus.INSTALLED

        return ModelStatus.NOT_INSTALLED

    def download_model(self, model_id: str) -> Dict:
        """
        下载模型

        Args:
            model_id: 模型 ID

        Returns:
            下载任务信息
        """
        if model_id not in AVAILABLE_MODELS:
            raise ValueError(f"未知的模型 ID: {model_id}")

        model_info = AVAILABLE_MODELS[model_id]

        if model_info.provider == "ollama":
            return self._download_ollama_model(model_info)
        elif model_info.provider == "huggingface":
            return self._download_huggingface_model(model_info)
        elif model_info.provider == "openai":
            return {"status": "success", "message": "API 模型无需下载，请配置 API Key"}

        raise ValueError(f"不支持的模型提供商: {model_info.provider}")

    def _download_ollama_model(self, model_info: ModelInfo) -> Dict:
        """下载 Ollama 模型"""
        try:
            # 启动后台下载
            subprocess.Popen(
                ['ollama', 'pull', model_info.model_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            logger.info(f"开始下载 Ollama 模型: {model_info.model_id}")
            return {
                "status": "downloading",
                "message": f"正在后台下载 {model_info.name}，请稍候..."
            }

        except FileNotFoundError:
            return {
                "status": "error",
                "message": "Ollama 未安装，请先安装 Ollama: https://ollama.ai"
            }

    def _download_huggingface_model(self, model_info: ModelInfo) -> Dict:
        """下载 HuggingFace 模型"""
        # HuggingFace 模型会在首次使用时自动下载
        return {
            "status": "pending",
            "message": f"{model_info.name} 将在首次使用时自动下载"
        }

    def set_active_model(self, model_id: str) -> Dict:
        """
        设置激活的模型

        Args:
            model_id: 模型 ID

        Returns:
            操作结果
        """
        if model_id not in AVAILABLE_MODELS:
            raise ValueError(f"未知的模型 ID: {model_id}")

        model_info = AVAILABLE_MODELS[model_id]

        # 检查模型是否已安装
        status = self._check_model_status(model_info)
        if status == ModelStatus.NOT_INSTALLED:
            return {
                "status": "error",
                "message": f"{model_info.name} 尚未安装，请先下载"
            }

        # 设置激活模型
        if model_info.type == ModelType.LLM:
            self.config['active_llm'] = model_id
        elif model_info.type == ModelType.EMBEDDING:
            self.config['active_embedding'] = model_id

        self._save_config()

        logger.info(f"已切换到模型: {model_info.name}")
        return {
            "status": "success",
            "message": f"已切换到 {model_info.name}"
        }

    def set_api_key(self, provider: str, api_key: str) -> Dict:
        """
        设置 API Key

        Args:
            provider: 提供商（openai 等）
            api_key: API Key

        Returns:
            操作结果
        """
        if 'api_keys' not in self.config:
            self.config['api_keys'] = {}

        self.config['api_keys'][provider] = api_key
        self._save_config()

        logger.info(f"已设置 {provider} API Key")
        return {
            "status": "success",
            "message": f"已设置 {provider} API Key"
        }

    def get_active_models(self) -> Dict:
        """获取当前激活的模型"""
        return {
            "llm": self.config.get('active_llm'),
            "embedding": self.config.get('active_embedding')
        }

    def get_all_status(self) -> Dict[str, dict]:
        """返回所有模型的运行时状态 {model_id: {status, download_progress, is_active}}"""
        result = {}
        active_llm = self.config.get('active_llm')
        active_emb = self.config.get('active_embedding')
        downloading = self.config.get('downloading', {})

        for model_id, info in AVAILABLE_MODELS.items():
            if model_id in downloading:
                status = 'downloading'
                progress = downloading[model_id].get('progress', 0)
            elif self._is_installed(model_id, info):
                status = 'installed'
                progress = 100
            else:
                status = 'not_installed'
                progress = 0

            is_active = (model_id == active_llm or model_id == active_emb)
            if is_active:
                status = 'active'

            result[model_id] = {
                'status': status,
                'download_progress': progress,
                'is_active': is_active,
            }
        return result

    def set_config_field(self, model_id: str, field_key: str, value: str) -> None:
        """保存模型的某个配置字段（如 api_key、base_url）"""
        if 'model_configs' not in self.config:
            self.config['model_configs'] = {}
        if model_id not in self.config['model_configs']:
            self.config['model_configs'][model_id] = {}
        self.config['model_configs'][model_id][field_key] = value
        # 同时更新 api_keys 以保持向后兼容
        if field_key == 'api_key':
            provider = AVAILABLE_MODELS[model_id].provider if model_id in AVAILABLE_MODELS else model_id
            if 'api_keys' not in self.config:
                self.config['api_keys'] = {}
            self.config['api_keys'][provider] = value
        self._save_config()

    def validate_api_key(self, model_id: str) -> tuple:
        """
        验证模型的 API Key 是否有效。
        Returns: (ok: bool, message: str)
        """
        if model_id not in AVAILABLE_MODELS:
            return False, f"未知模型 {model_id}"

        info = AVAILABLE_MODELS[model_id]
        cfg = self.config.get('model_configs', {}).get(model_id, {})
        api_key = cfg.get('api_key') or self.config.get('api_keys', {}).get(info.provider, '')

        if not api_key:
            return False, "未配置 API Key"

        try:
            import urllib.request, json as _json
            provider = info.provider

            if provider == 'openai':
                base_url = cfg.get('base_url', 'https://api.openai.com/v1')
                req = urllib.request.Request(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                urllib.request.urlopen(req, timeout=5)
                return True, "API Key 有效"

            elif provider == 'anthropic':
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=_json.dumps({"model": "claude-3-haiku-20240307", "max_tokens": 1,
                                      "messages": [{"role": "user", "content": "hi"}]}).encode(),
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
                return True, "API Key 有效"

            elif provider == 'deepseek':
                req = urllib.request.Request(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                urllib.request.urlopen(req, timeout=5)
                return True, "API Key 有效"

            elif provider in ('tongyi', 'kimi', 'doubao'):
                # 这些 provider 暂时只做格式校验
                if len(api_key) > 10:
                    return True, "API Key 格式正确（未做在线验证）"
                return False, "API Key 格式不正确"

            else:
                return True, "已保存（未做在线验证）"

        except Exception as e:
            err = str(e)
            if '401' in err or 'Unauthorized' in err:
                return False, "API Key 无效或已过期"
            if '403' in err:
                return False, "API Key 权限不足"
            return False, f"验证失败: {err}"

    def _ollama_names_for_model(self, model_id: str) -> list[str]:
        if model_id.startswith('qwen2.5-'):
            return [model_id.replace('qwen2.5-', 'qwen2.5:')]
        if model_id.startswith('qwen3.5-'):
            return [model_id.replace('qwen3.5-', 'qwen3.5:')]
        if model_id.startswith('llama3.2-'):
            return [model_id.replace('llama3.2-', 'llama3.2:')]
        if model_id.startswith('gemma2-'):
            return [model_id.replace('gemma2-', 'gemma2:')]
        if model_id.startswith('deepseek-r1-'):
            return [model_id.replace('deepseek-r1-', 'deepseek-r1:')]
        return [model_id]

    def _is_installed(self, model_id: str, info) -> bool:
        """检查模型是否已安装"""
        if info.provider == 'ollama':
            try:
                import urllib.request
                resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
                data = __import__('json').loads(resp.read())
                installed = {m['name'] for m in data.get('models', [])}
                aliases = self._ollama_names_for_model(model_id)
                return any(alias == name or name.startswith(f"{alias}:") for alias in aliases for name in installed)
            except Exception:
                return False
        elif info.provider == 'huggingface':
            hf_dir = Path.home() / '.cache' / 'huggingface' / 'hub'
            return any(hf_dir.glob(f"*{model_id}*"))
        elif info.requires_api_key:
            # 商业模型：有 api_key 配置即视为"已安装"
            cfg = self.config.get('model_configs', {}).get(model_id, {})
            return bool(cfg.get('api_key') or
                        self.config.get('api_keys', {}).get(info.provider, ''))
        return False

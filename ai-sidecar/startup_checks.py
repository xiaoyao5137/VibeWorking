"""
启动前置检查 - 确保必要的模型已安装
"""

import logging
import sys
import subprocess

logger = logging.getLogger(__name__)


def check_ollama_installed() -> bool:
    """检查 Ollama 是否已安装"""
    try:
        result = subprocess.run(
            ["which", "ollama"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def check_ollama_running() -> bool:
    """检查 Ollama 服务是否运行"""
    try:
        from ollama import Client
        client = Client()
        client.list()
        return True
    except Exception:
        return False


def check_model_available(model_name: str = "qwen2.5:3b") -> bool:
    """检查指定模型是否已下载"""
    try:
        from ollama import Client
        client = Client()
        models = client.list()

        # 检查模型列表
        for model in models.get('models', []):
            # ollama 客户端返回的是对象，直接访问 model 属性
            if hasattr(model, 'model') and model.model == model_name:
                return True
        return False
    except Exception:
        return False


def check_embedding_model() -> bool:
    """检查向量模型是否可用"""
    try:
        from embedding.model import EmbeddingModel
        model = EmbeddingModel.create_default()
        # 测试编码
        model.encode(["测试"])
        return True
    except Exception as e:
        logger.error(f"向量模型检查失败: {e}")
        return False


def run_startup_checks() -> bool:
    """
    运行启动前置检查

    Returns:
        True 如果所有检查通过，False 否则
    """
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔍 记忆面包启动前置检查")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    all_passed = True

    # 1. 检查 Ollama 安装
    print("1️⃣  检查 Ollama 安装...")
    if check_ollama_installed():
        print("   ✅ Ollama 已安装")
    else:
        print("   ❌ Ollama 未安装")
        print("   📝 安装方法：brew install ollama")
        all_passed = False

    print()

    # 2. 检查 Ollama 服务
    print("2️⃣  检查 Ollama 服务...")
    if check_ollama_running():
        print("   ✅ Ollama 服务运行中")
    else:
        print("   ❌ Ollama 服务未运行")
        print("   📝 启动方法：ollama serve")
        all_passed = False

    print()

    # 3. 检查推理模型
    print("3️⃣  检查推理模型 (qwen2.5:3b)...")
    if check_model_available("qwen2.5:3b"):
        print("   ✅ 推理模型已下载")
    else:
        print("   ❌ 推理模型未下载")
        print("   📝 下载方法：ollama pull qwen2.5:3b")
        all_passed = False

    print()

    # 4. 检查向量模型
    print("4️⃣  检查向量模型 (BGE-M3)...")
    if check_embedding_model():
        print("   ✅ 向量模型已加载")
    else:
        print("   ❌ 向量模型未加载")
        print("   📝 模型会自动下载，请检查网络连接")
        all_passed = False

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if all_passed:
        print("✅ 所有检查通过，可以启动记忆面包")
    else:
        print("❌ 部分检查未通过，请先完成上述配置")
        print()
        print("📚 快速配置指南：")
        print("   1. 安装 Ollama: brew install ollama")
        print("   2. 启动 Ollama: ollama serve &")
        print("   3. 下载模型: ollama pull qwen2.5:3b")
        print("   4. 重新启动记忆面包")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    return all_passed


if __name__ == "__main__":
    if not run_startup_checks():
        sys.exit(1)

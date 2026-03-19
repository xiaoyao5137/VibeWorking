"""
模型管理 API - 提供模型列表、下载、配置等接口
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from model_manager import ModelManager, ModelType
from model_registry import AVAILABLE_MODELS, get_recommendations, get_model, list_models as registry_list
import psutil
import logging
import dataclasses

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# 初始化模型管理器
model_manager = ModelManager()


def _model_to_dict(meta, status_info: dict) -> dict:
    """将 ModelMeta + 状态信息合并为前端所需的 dict"""
    d = dataclasses.asdict(meta)
    d['status']            = status_info.get('status', 'not_installed')
    d['download_progress'] = status_info.get('download_progress', 0)
    d['is_active']         = status_info.get('is_active', False)
    d['recommended']       = status_info.get('recommended', False)
    d['recommend_reason']  = status_info.get('recommend_reason', '')
    return d


@app.route('/api/models', methods=['GET'])
def list_models():
    """
    获取所有可用模型列表（整合 registry + 运行时状态）

    Query Parameters:
        category: 筛选类型（llm/embedding/ocr/asr/vlm）
    """
    try:
        category = request.args.get('category')
        metas = registry_list(category)

        # 获取运行时状态
        runtime = model_manager.get_all_status()
        # 获取推荐列表
        hw = _get_hardware()
        rec = get_recommendations(
            memory_gb=hw['memory_gb'],
            cpu_cores=hw['cpu_cores'],
            disk_free_gb=hw['disk_free_gb'],
            has_gpu=hw['has_gpu'],
        )
        recommended_ids = set(rec['recommended_ids'])

        result = []
        for meta in metas:
            status_info = runtime.get(meta.id, {})
            status_info['recommended'] = meta.id in recommended_ids
            status_info['recommend_reason'] = rec['reason'] if meta.id in recommended_ids else ''
            result.append(_model_to_dict(meta, status_info))

        return jsonify({'status': 'ok', 'models': result})
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/hardware', methods=['GET'])
def get_hardware():
    """检测本机硬件配置并返回选型建议"""
    try:
        hw = _get_hardware()
        rec = get_recommendations(
            memory_gb=hw['memory_gb'],
            cpu_cores=hw['cpu_cores'],
            disk_free_gb=hw['disk_free_gb'],
            has_gpu=hw['has_gpu'],
            gpu_memory_gb=hw.get('gpu_memory_gb', 0.0),
        )
        return jsonify({'status': 'ok', 'hardware': hw, 'recommendation': rec})
    except Exception as e:
        logger.error(f"硬件检测失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/active', methods=['GET'])
def get_active_models():
    """返回当前激活的 LLM 和 Embedding 模型"""
    try:
        active_llm_id  = model_manager.config.get('active_llm')
        active_emb_id  = model_manager.config.get('active_embedding')
        runtime        = model_manager.get_all_status()

        def _build(model_id):
            if not model_id:
                return None
            meta = get_model(model_id)
            if not meta:
                return None
            return _model_to_dict(meta, runtime.get(model_id, {'status': 'installed', 'is_active': True}))

        return jsonify({
            'status': 'ok',
            'llm':       _build(active_llm_id),
            'embedding': _build(active_emb_id),
        })
    except Exception as e:
        logger.error(f"获取激活模型失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/<model_id>/status', methods=['GET'])
def model_status(model_id: str):
    """查询单个模型的下载状态（用于前端轮询进度）"""
    try:
        runtime = model_manager.get_all_status()
        info = runtime.get(model_id, {'status': 'not_installed', 'download_progress': 0})
        return jsonify({'status': 'ok', 'model_id': model_id, **info})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/<model_id>/configure', methods=['POST'])
def configure_model(model_id: str):
    """
    保存模型的 API Key 及其他配置字段

    Body: { "fields": { "api_key": "sk-...", "base_url": "..." } }
    """
    try:
        data   = request.json or {}
        fields = data.get('fields', {})
        meta   = get_model(model_id)
        if not meta:
            return jsonify({'status': 'error', 'message': f'未知模型 {model_id}'}), 404

        # 保存各字段
        for field_def in (meta.api_key_fields or []):
            if field_def.key in fields:
                model_manager.set_config_field(model_id, field_def.key, fields[field_def.key])

        return jsonify({'status': 'ok', 'message': f'{model_id} 配置已保存'})
    except Exception as e:
        logger.error(f"配置模型失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/<model_id>/validate', methods=['POST'])
def validate_model(model_id: str):
    """验证 API Key 是否有效（发送测试请求）"""
    try:
        ok, msg = model_manager.validate_api_key(model_id)
        return jsonify({'status': 'ok' if ok else 'error', 'valid': ok, 'message': msg})
    except Exception as e:
        return jsonify({'status': 'error', 'valid': False, 'message': str(e)}), 500


@app.route('/api/models/<model_id>/download', methods=['POST'])
def download_model(model_id: str):
    try:
        success = model_manager.download_model(model_id)
        if success:
            return jsonify({'status': 'ok', 'message': f'模型 {model_id} 下载已启动'})
        return jsonify({'status': 'error', 'message': f'模型 {model_id} 下载失败'}), 500
    except Exception as e:
        logger.error(f"下载模型失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/<model_id>/activate', methods=['POST'])
def activate_model(model_id: str):
    try:
        success = model_manager.activate_model(model_id)
        if success:
            return jsonify({'status': 'ok', 'message': f'模型 {model_id} 已激活'})
        return jsonify({'status': 'error', 'message': f'模型 {model_id} 激活失败'}), 500
    except Exception as e:
        logger.error(f"激活模型失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/<model_id>/delete', methods=['DELETE'])
def delete_model(model_id: str):
    try:
        success = model_manager.delete_model(model_id)
        if success:
            return jsonify({'status': 'ok', 'message': f'模型 {model_id} 已删除'})
        return jsonify({'status': 'error', 'message': f'模型 {model_id} 删除失败'}), 500
    except Exception as e:
        logger.error(f"删除模型失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/config', methods=['GET'])
def get_config():
    try:
        return jsonify({'status': 'ok', 'config': model_manager.config})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/models/config/api-key', methods=['POST'])
def set_api_key():
    try:
        data     = request.json or {}
        provider = data.get('provider')
        api_key  = data.get('api_key')
        if not provider or not api_key:
            return jsonify({'status': 'error', 'message': '缺少 provider 或 api_key'}), 400
        model_manager.set_api_key(provider, api_key)
        return jsonify({'status': 'ok', 'message': f'{provider} API Key 已设置'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _get_hardware() -> dict:
    mem   = psutil.virtual_memory()
    disk  = psutil.disk_usage('/')
    cpu   = psutil.cpu_count(logical=False) or psutil.cpu_count()
    hw = {
        'memory_gb':    round(mem.total / (1024 ** 3), 1),
        'cpu_cores':    cpu,
        'disk_free_gb': round(disk.free / (1024 ** 3), 1),
        'has_gpu':      False,
        'gpu_memory_gb': 0.0,
    }
    # 尝试检测 GPU（macOS Metal / NVIDIA）
    try:
        import subprocess
        result = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True, text=True, timeout=3
        )
        if 'VRAM' in result.stdout or 'Metal' in result.stdout:
            hw['has_gpu'] = True
    except Exception:
        pass
    return hw


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=7071, debug=True)


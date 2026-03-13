"""
模型管理 API - 提供模型列表、下载、配置等接口
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from model_manager import ModelManager, ModelType
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# 初始化模型管理器
model_manager = ModelManager()


@app.route('/api/models', methods=['GET'])
def list_models():
    """
    获取所有可用模型列表

    Query Parameters:
        type: 筛选模型类型（llm/embedding）
    """
    try:
        model_type = request.args.get('type')
        if model_type:
            model_type = ModelType(model_type)

        models = model_manager.list_models(model_type)

        return jsonify({
            'status': 'ok',
            'models': models
        })
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/models/<model_id>/download', methods=['POST'])
def download_model(model_id: str):
    """
    下载指定模型

    Path Parameters:
        model_id: 模型 ID
    """
    try:
        success = model_manager.download_model(model_id)

        if success:
            return jsonify({
                'status': 'ok',
                'message': f'模型 {model_id} 下载成功'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'模型 {model_id} 下载失败'
            }), 500

    except Exception as e:
        logger.error(f"下载模型失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/models/<model_id>/activate', methods=['POST'])
def activate_model(model_id: str):
    """
    激活指定模型

    Path Parameters:
        model_id: 模型 ID
    """
    try:
        success = model_manager.activate_model(model_id)

        if success:
            return jsonify({
                'status': 'ok',
                'message': f'模型 {model_id} 已激活'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'模型 {model_id} 激活失败'
            }), 500

    except Exception as e:
        logger.error(f"激活模型失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/models/<model_id>/delete', methods=['DELETE'])
def delete_model(model_id: str):
    """
    删除指定模型

    Path Parameters:
        model_id: 模型 ID
    """
    try:
        success = model_manager.delete_model(model_id)

        if success:
            return jsonify({
                'status': 'ok',
                'message': f'模型 {model_id} 已删除'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'模型 {model_id} 删除失败'
            }), 500

    except Exception as e:
        logger.error(f"删除模型失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/models/config', methods=['GET'])
def get_config():
    """获取当前模型配置"""
    try:
        return jsonify({
            'status': 'ok',
            'config': model_manager.config
        })
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/models/config/api-key', methods=['POST'])
def set_api_key():
    """
    设置 API Key

    Body:
        {
            "provider": "openai",
            "api_key": "sk-..."
        }
    """
    try:
        data = request.json
        provider = data.get('provider')
        api_key = data.get('api_key')

        if not provider or not api_key:
            return jsonify({
                'status': 'error',
                'message': '缺少 provider 或 api_key'
            }), 400

        model_manager.set_api_key(provider, api_key)

        return jsonify({
            'status': 'ok',
            'message': f'{provider} API Key 已设置'
        })

    except Exception as e:
        logger.error(f"设置 API Key 失败: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=7071, debug=True)

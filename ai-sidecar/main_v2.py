"""
主入口文件（集成闲时计算）

启动 AI Sidecar 服务，包含：
1. IPC 服务器（Unix Domain Socket）
2. 闲时计算引擎
3. 后台任务处理
4. 内部向量搜索 HTTP 服务（端口 7072，供 model_api_server 调用）
"""

import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path

from dispatcher_v2 import Dispatcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/memory-bread-sidecar.log')
    ]
)
logger = logging.getLogger(__name__)


def _start_vector_search_server():
    """在独立线程中启动内部向量搜索 HTTP 服务（端口 7072）。

    该服务在 sidecar 进程内运行，复用 VectorStorage 单例已有的 Qdrant 客户端，
    避免 model_api_server 另开 Qdrant 连接导致文件锁冲突。
    """
    try:
        from flask import Flask, jsonify, request as flask_request

        _vs_app = Flask("vector_search_internal")

        @_vs_app.route('/vector_search', methods=['POST'])
        def vector_search():
            data = flask_request.get_json()
            if not data or 'query_vector' not in data:
                return jsonify({'error': 'missing query_vector'}), 400
            query_vector = data['query_vector']
            top_k = int(data.get('top_k', 10))
            score_threshold = float(data.get('score_threshold', 0.3))

            try:
                from embedding.vector_storage import get_vector_storage
                vs = get_vector_storage()
                client = vs._get_qdrant_client()
                if client is None:
                    return jsonify({'error': 'Qdrant client not available'}), 503

                results = client.query_points(
                    collection_name=vs._collection_name,
                    query=query_vector,
                    limit=top_k,
                    score_threshold=score_threshold,
                ).points

                hits = []
                for hit in results:
                    payload = dict(hit.payload or {})
                    capture_id = int(payload.get('capture_id') or 0)
                    doc_key = payload.get('doc_key') or f"capture:{capture_id}"
                    hits.append({
                        'capture_id': capture_id,
                        'doc_key': doc_key,
                        'text': payload.get('text', ''),
                        'score': float(hit.score),
                        'source': 'vector',
                        'metadata': payload,
                    })
                return jsonify({'results': hits})
            except Exception as e:
                logger.error("vector_search 失败: %s", e)
                return jsonify({'error': str(e)}), 500

        @_vs_app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'ok', 'service': 'vector_search'})

        logger.info("启动内部向量搜索服务 (port 7072)...")
        _vs_app.run(host='127.0.0.1', port=7072, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        logger.warning("内部向量搜索服务启动失败（不影响主服务）: %s", e)


class SidecarServer:
    """AI Sidecar 服务器"""

    def __init__(self, socket_path: str = "/tmp/memory-bread-sidecar.sock"):
        self.socket_path = socket_path
        self.dispatcher = Dispatcher()
        self.server = None
        self.running = False

    async def start(self) -> None:
        """启动服务器"""
        logger.info("=" * 60)
        logger.info("记忆面包 AI Sidecar 启动中...")
        logger.info("=" * 60)

        # 1. 初始化 Dispatcher（包含闲时计算系统）
        await self.dispatcher.initialize()

        # 2. 清理旧的 socket 文件
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()
            logger.info("已清理旧的 socket 文件")

        # 3. 启动 Unix Domain Socket 服务器
        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path
        )

        self.running = True
        logger.info("✓ IPC 服务器已启动: %s", self.socket_path)
        logger.info("=" * 60)
        logger.info("系统就绪，等待请求...")
        logger.info("=" * 60)

        # 4. 运行服务器
        async with self.server:
            await self.server.serve_forever()

    async def stop(self) -> None:
        """停止服务器"""
        logger.info("正在停止 AI Sidecar...")

        self.running = False

        # 停止 IPC 服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # 停止闲时计算引擎
        if self.dispatcher._idle_engine:
            await self.dispatcher._idle_engine.stop()

        logger.info("AI Sidecar 已停止")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """处理客户端连接"""
        try:
            # 读取请求长度（4 字节大端）
            length_bytes = await reader.readexactly(4)
            length = int.from_bytes(length_bytes, byteorder='big')

            # 读取请求内容
            request_bytes = await reader.readexactly(length)
            request_json = request_bytes.decode('utf-8')

            # 解析请求
            from memory_bread_ipc import IpcRequest
            request = IpcRequest.from_json(request_json)

            logger.debug("收到请求: id=%s type=%s", request.id, request.task.type)

            # 分发请求
            response = await self.dispatcher.dispatch(request)

            # 发送响应
            response_json = response.to_json()
            response_bytes = response_json.encode('utf-8')
            response_length = len(response_bytes).to_bytes(4, byteorder='big')

            writer.write(response_length)
            writer.write(response_bytes)
            await writer.drain()

            logger.debug("响应已发送: id=%s status=%s", response.id, response.status)

        except asyncio.IncompleteReadError:
            logger.debug("客户端断开连接")
        except Exception as e:
            logger.error("处理请求时出错: %s", e, exc_info=True)
        finally:
            writer.close()
            await writer.wait_closed()


async def main():
    """主函数"""
    server = SidecarServer()

    # 启动内部向量搜索 HTTP 服务（daemon 线程，进程退出时自动结束）
    vs_thread = threading.Thread(target=_start_vector_search_server, daemon=True, name="vector-search-server")
    vs_thread.start()

    # 注册信号处理
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("收到停止信号")
        asyncio.create_task(server.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # 启动服务器
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("收到键盘中断")
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序退出")

"""
主入口文件（集成闲时计算）

启动 AI Sidecar 服务，包含：
1. IPC 服务器（Unix Domain Socket）
2. 闲时计算引擎
3. 后台任务处理
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from dispatcher_v2 import Dispatcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/workbuddy-sidecar.log')
    ]
)
logger = logging.getLogger(__name__)


class SidecarServer:
    """AI Sidecar 服务器"""

    def __init__(self, socket_path: str = "/tmp/workbuddy-sidecar.sock"):
        self.socket_path = socket_path
        self.dispatcher = Dispatcher()
        self.server = None
        self.running = False

    async def start(self) -> None:
        """启动服务器"""
        logger.info("=" * 60)
        logger.info("WorkBuddy AI Sidecar 启动中...")
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
            from workbuddy_ipc import IpcRequest
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

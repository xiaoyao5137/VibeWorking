"""
定时任务执行 API Server（端口 7071）

Rust 调度器通过 HTTP POST /tasks/execute 触发任务执行。
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from scheduled_task_executor import TaskExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="记忆面包 Task Executor", version="1.0.0")

DB_PATH = str(Path.home() / ".memory-bread" / "memory-bread.db")
executor = TaskExecutor(db_path=DB_PATH)


class ExecuteRequest(BaseModel):
    task_id: int


@app.post("/tasks/execute")
def execute_task(req: ExecuteRequest):
    """Rust 调度器调用此接口触发任务执行"""
    logger.info(f"收到任务执行请求: task_id={req.task_id}")
    result = executor.execute_task(req.task_id)
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "执行失败"))
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7071, log_level="info")

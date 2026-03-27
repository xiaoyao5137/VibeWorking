"""
系统资源采样器

每 30 秒采样一次 CPU、内存、磁盘 IO，写入 system_metrics 表。
在闲时计算期间加密采样（每 10 秒一次），便于定位卡顿原因。
"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

DB_PATH = str(Path.home() / ".memory-bread" / "memory-bread.db")
_PROCESS = psutil.Process(os.getpid())
_GPU_NAME_CACHE: str | None | bool = False
_GPU_IOREG_CLASS_CACHE: str | None | bool = False
_PREV_PROCESS_CPU_TIMES: dict[int, tuple[float, float, float]] = {}
LOG_DIR = Path.home() / ".memory-bread" / "logs"
SIDECAR_PID_FILE = LOG_DIR / "sidecar.pid"
MODEL_API_PID_FILE = LOG_DIR / "model_api.pid"
CORE_PID_FILE = LOG_DIR / "core.pid"
UI_PID_FILE = LOG_DIR / "ui.pid"
MODEL_RUNTIME_PORTS = {11434}
_SCOPE_SYSTEM = "system_global"
_SCOPE_SUITE = "app_suite_total"
_SCOPE_MODEL = "model_process_total"
_SOURCE = "ai_sidecar"


@dataclass
class ScopeMetrics:
    scope: str
    target_name: str
    cpu_percent: float
    mem_process_mb: int
    pids: list[int]
    coverage_status: str = "exact"
    coverage_note: Optional[str] = None


@dataclass
class SystemSnapshot:
    cpu_total: float
    mem_total_mb: int
    mem_used_mb: int
    mem_percent: float
    disk_read_mb: float
    disk_write_mb: float
    gpu_percent: float | None
    gpu_name: str | None


def _run_command(command: list[str], timeout: int = 3) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return result.stdout or result.stderr or ""
        return result.stdout
    except Exception:
        return ""


def _get_available_mb() -> int:
    return int(psutil.virtual_memory().available / 1024 / 1024)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(system_metrics)")
    existing = {row[1] for row in cursor.fetchall()}

    column_defs = {
        "context": "TEXT",
        "gpu_percent": "REAL",
        "gpu_name": "TEXT",
        "source": "TEXT",
        "scope": "TEXT",
        "target_name": "TEXT",
        "target_pid": "INTEGER",
        "target_pids_json": "TEXT",
        "coverage_status": "TEXT",
        "coverage_note": "TEXT",
    }
    for column, definition in column_defs.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE system_metrics ADD COLUMN {column} {definition}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_scope_ts ON system_metrics(scope, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_source_ts ON system_metrics(source, ts)")


def _detect_gpu_name() -> str | None:
    global _GPU_NAME_CACHE
    if _GPU_NAME_CACHE is not False:
        return _GPU_NAME_CACHE or None

    gpu_name = os.getenv("WORKBUDDY_GPU_NAME")
    if not gpu_name:
        output = _run_command(["system_profiler", "SPDisplaysDataType"], timeout=3)
        for line in output.splitlines():
            text = line.strip()
            if text.startswith("Chipset Model:") or text.startswith("型号名称:"):
                gpu_name = text.split(":", 1)[1].strip()
                break
            if text.startswith("Model:"):
                gpu_name = text.split(":", 1)[1].strip()
                break

    _GPU_NAME_CACHE = gpu_name or None
    return gpu_name or None


def _detect_ioreg_gpu_class() -> str | None:
    global _GPU_IOREG_CLASS_CACHE
    if _GPU_IOREG_CLASS_CACHE is not False:
        return _GPU_IOREG_CLASS_CACHE or None

    for class_name in ("AGXAccelerator", "IOAccelerator"):
        output = _run_command(["ioreg", "-r", "-d1", "-w0", "-c", class_name], timeout=3)
        if "PerformanceStatistics" in output:
            _GPU_IOREG_CLASS_CACHE = class_name
            return class_name

    _GPU_IOREG_CLASS_CACHE = None
    return None


def _extract_ioreg_number(output: str, field: str) -> float | None:
    idx = output.find(f'"{field}"')
    if idx == -1:
        return None

    idx = output.find('=', idx)
    if idx == -1:
        return None

    start = idx + 1
    end = start
    while end < len(output) and output[end] not in ',}\n':
        end += 1

    raw = output[start:end].strip().strip('"')
    try:
        return float(raw)
    except Exception:
        return None


def _sample_gpu_percent() -> float | None:
    raw = os.getenv("WORKBUDDY_GPU_PERCENT")
    if raw:
        try:
            value = float(raw)
            return max(0.0, min(100.0, value))
        except Exception:
            pass

    class_name = _detect_ioreg_gpu_class()
    if not class_name:
        return None

    output = _run_command(["ioreg", "-r", "-d1", "-w0", "-c", class_name], timeout=3)
    if not output:
        return None

    for field in ("Device Utilization %", "Renderer Utilization %", "Tiler Utilization %"):
        value = _extract_ioreg_number(output, field)
        if value is not None:
            return max(0.0, min(100.0, value))

    return None


def _safe_process(pid: int) -> psutil.Process | None:
    try:
        return psutil.Process(pid)
    except (psutil.Error, ValueError):
        return None


def _read_pid_file(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _process_cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except (psutil.Error, TypeError):
        return ""


def _process_name(proc: psutil.Process) -> str:
    try:
        return proc.name().lower()
    except psutil.Error:
        return ""


def _matches_expected(proc: psutil.Process, expected: str) -> bool:
    cmdline = _process_cmdline(proc)
    return expected in cmdline


def _descendant_pids(proc: psutil.Process) -> set[int]:
    pids = {proc.pid}
    try:
        for child in proc.children(recursive=True):
            pids.add(child.pid)
    except psutil.Error:
        pass
    return pids


def _candidate_processes() -> list[psutil.Process]:
    result: list[psutil.Process] = []
    for proc in psutil.process_iter():
        try:
            result.append(proc)
        except psutil.Error:
            continue
    return result


def _collect_pids_from_pid_files() -> tuple[set[int], set[int]]:
    suite_pids: set[int] = set()
    model_pids: set[int] = set()
    pid_specs = [
        (SIDECAR_PID_FILE, "main.py", False),
        (MODEL_API_PID_FILE, "model_api_server.py", True),
        (CORE_PID_FILE, "memory-bread", False),
        (UI_PID_FILE, "tauri:dev", False),
    ]

    for pid_file, expected, is_model in pid_specs:
        pid = _read_pid_file(pid_file)
        if pid is None:
            continue
        proc = _safe_process(pid)
        if not proc or not _matches_expected(proc, expected):
            continue
        pids = _descendant_pids(proc)
        suite_pids.update(pids)
        if is_model:
            model_pids.update(pids)

    return suite_pids, model_pids


def _collect_pids_from_process_scan() -> tuple[set[int], set[int], list[str]]:
    suite_pids: set[int] = set()
    model_pids: set[int] = set()
    notes: list[str] = []

    for proc in _candidate_processes():
        cmdline = _process_cmdline(proc)
        lower_cmd = cmdline.lower()
        name = _process_name(proc)

        if any(token in lower_cmd for token in ("/ai-sidecar/main.py", " python main.py")):
            suite_pids.update(_descendant_pids(proc))
        elif "model_api_server.py" in lower_cmd:
            pids = _descendant_pids(proc)
            suite_pids.update(pids)
            model_pids.update(pids)
        elif "target/release/memory-bread" in lower_cmd or name == "memory-bread":
            suite_pids.update(_descendant_pids(proc))
        elif "tauri:dev" in lower_cmd or "vite" in lower_cmd or "memory-bread-desktop" in lower_cmd:
            suite_pids.update(_descendant_pids(proc))
        elif "ollama" in lower_cmd or name == "ollama":
            pids = _descendant_pids(proc)
            suite_pids.update(pids)
            model_pids.update(pids)
            notes.append("已纳入 Ollama 相关进程")

        try:
            connections = proc.net_connections(kind="inet")
        except (psutil.Error, AttributeError):
            connections = []
        for conn in connections:
            if conn.laddr and conn.laddr.port in MODEL_RUNTIME_PORTS:
                pids = _descendant_pids(proc)
                suite_pids.update(pids)
                model_pids.update(pids)
                notes.append(f"已纳入监听 {conn.laddr.port} 端口的模型运行时")
                break

    return suite_pids, model_pids, notes


def _sample_process_metrics(
    pids: set[int],
    target_name: str,
    scope: str,
    coverage_status: str = "exact",
    coverage_note: str | None = None,
) -> tuple[ScopeMetrics, dict[int, tuple[float, float, float]]]:
    cpu_percent = 0.0
    mem_process_mb = 0
    live_pids: list[int] = []
    current_times: dict[int, tuple[float, float, float]] = {}
    cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
    now_monotonic = time.monotonic()

    for pid in sorted(pids):
        proc = _safe_process(pid)
        if not proc:
            continue
        try:
            times = proc.cpu_times()
            current_total = float(times.user + times.system)
            create_time = float(proc.create_time())
            current_times[pid] = (create_time, current_total, now_monotonic)

            previous = _PREV_PROCESS_CPU_TIMES.get(pid)
            if previous and previous[0] == create_time:
                elapsed = max(0.0, now_monotonic - previous[2])
                delta_cpu = max(0.0, current_total - previous[1])
                if elapsed > 0:
                    cpu_percent += min(100.0, delta_cpu * 100.0 / elapsed / cpu_count)

            mem_process_mb += int(proc.memory_info().rss / 1024 / 1024)
            live_pids.append(pid)
        except psutil.Error:
            continue

    metrics = ScopeMetrics(
        scope=scope,
        target_name=target_name,
        cpu_percent=max(0.0, cpu_percent),
        mem_process_mb=max(0, mem_process_mb),
        pids=live_pids,
        coverage_status=coverage_status,
        coverage_note=coverage_note,
    )
    return metrics, current_times


def _aggregate_processes(pids: set[int], target_name: str, scope: str, coverage_status: str = "exact", coverage_note: str | None = None) -> ScopeMetrics:
    global _PREV_PROCESS_CPU_TIMES

    metrics, current_times = _sample_process_metrics(pids, target_name, scope, coverage_status, coverage_note)
    _PREV_PROCESS_CPU_TIMES = {
        pid: value
        for pid, value in _PREV_PROCESS_CPU_TIMES.items()
        if pid in current_times
    }
    _PREV_PROCESS_CPU_TIMES.update(current_times)
    return metrics


def _collect_scope_metrics() -> tuple[ScopeMetrics, ScopeMetrics]:
    global _PREV_PROCESS_CPU_TIMES

    suite_pids, model_pids = _collect_pids_from_pid_files()
    scan_suite_pids, scan_model_pids, notes = _collect_pids_from_process_scan()
    suite_pids.update(scan_suite_pids)
    model_pids.update(scan_model_pids)

    suite_note = None
    if not suite_pids:
        suite_status = "unavailable"
        suite_note = "未识别到记忆面包相关进程"
    else:
        suite_status = "exact" if _read_pid_file(SIDECAR_PID_FILE) or _read_pid_file(CORE_PID_FILE) else "partial"

    if not model_pids:
        model_status = "unavailable"
        model_note = "未识别模型进程"
    else:
        model_status = "partial" if notes else "exact"
        unique_notes = list(dict.fromkeys(notes))
        if any("11434" in note for note in unique_notes):
            model_note = "含 Ollama / 11434 运行时"
        elif any("Ollama" in note for note in unique_notes):
            model_note = "含 Ollama 运行时"
        elif unique_notes:
            model_note = "已合并模型运行时"
        else:
            model_note = None

    suite_metrics, suite_times = _sample_process_metrics(suite_pids, "memory_bread_suite", _SCOPE_SUITE, suite_status, suite_note)
    model_metrics, model_times = _sample_process_metrics(model_pids, "model_runtime", _SCOPE_MODEL, model_status, model_note)

    live_times = {**suite_times, **model_times}
    _PREV_PROCESS_CPU_TIMES = {
        pid: value
        for pid, value in _PREV_PROCESS_CPU_TIMES.items()
        if pid in live_times
    }
    _PREV_PROCESS_CPU_TIMES.update(live_times)

    return suite_metrics, model_metrics


def _sample_system_snapshot(prev_disk_counters) -> tuple[SystemSnapshot, object]:
    cpu_total = psutil.cpu_percent(interval=0.2)
    vm = psutil.virtual_memory()
    mem_total_mb = int(vm.total / 1024 / 1024)
    mem_used_mb = max(0, mem_total_mb - int(vm.available / 1024 / 1024))
    mem_percent = (mem_used_mb / mem_total_mb * 100.0) if mem_total_mb > 0 else 0.0

    curr_disk = psutil.disk_io_counters()
    disk_read_mb = 0.0
    disk_write_mb = 0.0
    if prev_disk_counters and curr_disk:
        disk_read_mb = (curr_disk.read_bytes - prev_disk_counters.read_bytes) / 1024 / 1024
        disk_write_mb = (curr_disk.write_bytes - prev_disk_counters.write_bytes) / 1024 / 1024

    snapshot = SystemSnapshot(
        cpu_total=cpu_total,
        mem_total_mb=mem_total_mb,
        mem_used_mb=mem_used_mb,
        mem_percent=mem_percent,
        disk_read_mb=disk_read_mb,
        disk_write_mb=disk_write_mb,
        gpu_percent=_sample_gpu_percent(),
        gpu_name=_detect_gpu_name(),
    )
    return snapshot, curr_disk


def _insert_scope_metric(conn: sqlite3.Connection, ts: int, context: Optional[str], snapshot: SystemSnapshot, metrics: ScopeMetrics) -> None:
    target_pid = metrics.pids[0] if len(metrics.pids) == 1 else None
    conn.execute(
        """INSERT INTO system_metrics
           (ts, cpu_total, cpu_process, mem_total_mb, mem_used_mb, mem_percent,
            mem_process_mb, disk_read_mb, disk_write_mb, context, gpu_percent, gpu_name,
            source, scope, target_name, target_pid, target_pids_json, coverage_status, coverage_note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts,
            snapshot.cpu_total,
            metrics.cpu_percent,
            snapshot.mem_total_mb,
            snapshot.mem_used_mb,
            snapshot.mem_percent,
            metrics.mem_process_mb,
            snapshot.disk_read_mb if metrics.scope == _SCOPE_SYSTEM else 0.0,
            snapshot.disk_write_mb if metrics.scope == _SCOPE_SYSTEM else 0.0,
            context,
            snapshot.gpu_percent,
            snapshot.gpu_name,
            _SOURCE,
            metrics.scope,
            metrics.target_name,
            target_pid,
            json.dumps(metrics.pids, ensure_ascii=False),
            metrics.coverage_status,
            metrics.coverage_note,
        ),
    )


def _sample_once(
    db_path: str,
    context: Optional[str],
    prev_disk_counters,
):
    try:
        snapshot, curr_disk = _sample_system_snapshot(prev_disk_counters)
        suite_metrics, model_metrics = _collect_scope_metrics()
        ts = int(time.time() * 1000)
        conn = sqlite3.connect(db_path)
        _ensure_columns(conn)

        system_metrics = ScopeMetrics(
            scope=_SCOPE_SYSTEM,
            target_name="system",
            cpu_percent=0.0,
            mem_process_mb=0,
            pids=[],
            coverage_status="exact",
            coverage_note=None,
        )
        for metric in (system_metrics, suite_metrics, model_metrics):
            _insert_scope_metric(conn, ts, context, snapshot, metric)

        conn.commit()
        conn.close()
        return curr_disk
    except Exception as e:
        logger.warning(f"资源采样失败: {e}")
        return prev_disk_counters


class SystemMetricsSampler:
    NORMAL_INTERVAL = 30
    IDLE_INTERVAL = 10

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._running = False
        self._idle_mode = False
        self._task: Optional[asyncio.Task] = None
        self._prev_disk = None

    def set_idle_mode(self, active: bool):
        self._idle_mode = active
        logger.info(f"资源采样模式: {'闲时（10s）' if active else '正常（30s）'}")

    async def start(self):
        self._running = True
        psutil.cpu_percent(interval=None)
        _PROCESS.cpu_percent(interval=None)
        for proc in _candidate_processes():
            try:
                proc.cpu_percent(interval=None)
            except psutil.Error:
                continue
        self._prev_disk = psutil.disk_io_counters()
        self._task = asyncio.create_task(self._loop())
        logger.info("系统资源采样器已启动")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            interval = self.IDLE_INTERVAL if self._idle_mode else self.NORMAL_INTERVAL
            await asyncio.sleep(interval)
            context = "idle_compute" if self._idle_mode else "normal"
            self._prev_disk = _sample_once(self.db_path, context, self._prev_disk)


def snapshot(db_path: str = DB_PATH, context: str = "snapshot"):
    prev = psutil.disk_io_counters()
    _sample_once(db_path, context, prev)


def get_available_mb() -> int:
    return _get_available_mb()

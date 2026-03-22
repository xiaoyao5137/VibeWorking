#!/bin/bash
#
# 记忆面包 启动脚本
#
# 按顺序启动三个服务：
# 1. AI Sidecar (Python)
# 2. Core Engine (Rust)
# 3. Desktop UI (Tauri)
#

set -e  # 遇到错误立即退出

# 添加 Rust 到 PATH（如果存在）
if [ -d "$HOME/.cargo/bin" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 日志目录
LOG_DIR="$HOME/.memory-bread/logs"
mkdir -p "$LOG_DIR"

# PID 文件
SIDECAR_PID_FILE="$LOG_DIR/sidecar.pid"
MODEL_API_PID_FILE="$LOG_DIR/model_api.pid"
CORE_PID_FILE="$LOG_DIR/core.pid"
UI_PID_FILE="$LOG_DIR/ui.pid"

# 日志文件
SIDECAR_LOG="$LOG_DIR/sidecar.log"
MODEL_API_LOG="$LOG_DIR/model_api.log"
CORE_LOG="$LOG_DIR/core.log"
UI_LOG="$LOG_DIR/ui.log"

CORE_PORT=7070
MODEL_API_PORT=7071
UI_PORT=1420

# 打印带颜色的消息
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查进程是否运行
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

cleanup_port() {
    local port=$1
    local label=$2
    local pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        log_info "清理占用 ${port} 端口的进程（${label}）: $pids"
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
    fi
}

wait_for_http() {
    local url=$1
    local label=$2
    local retries=${3:-20}
    local delay=${4:-1}

    for ((i=1; i<=retries; i++)); do
        if curl -fsS "$url" > /dev/null 2>&1; then
            log_success "${label} 健康检查通过"
            return 0
        fi
        sleep "$delay"
    done

    log_warn "${label} 健康检查失败，请查看日志"
    return 1
}

show_status() {
    echo ""
    if is_running "$SIDECAR_PID_FILE"; then
        log_success "AI Sidecar: 运行中 (PID: $(cat "$SIDECAR_PID_FILE"))"
    else
        log_error "AI Sidecar: 未运行"
    fi

    if is_running "$MODEL_API_PID_FILE"; then
        log_success "Model API: 运行中 (PID: $(cat "$MODEL_API_PID_FILE"), Port: ${MODEL_API_PORT})"
    else
        log_error "Model API: 未运行"
    fi

    if is_running "$CORE_PID_FILE"; then
        log_success "Core Engine: 运行中 (PID: $(cat "$CORE_PID_FILE"), Port: ${CORE_PORT})"
    else
        log_error "Core Engine: 未运行"
    fi

    if is_running "$UI_PID_FILE"; then
        log_success "Desktop UI: 运行中 (PID: $(cat "$UI_PID_FILE"), Port: ${UI_PORT})"
    else
        log_error "Desktop UI: 未运行"
    fi
    echo ""
}

# 停止所有服务
stop_all() {
    log_info "停止所有服务..."

    # 停止 Desktop UI（包括子进程）
    if is_running "$UI_PID_FILE"; then
        local pid=$(cat "$UI_PID_FILE")
        log_info "停止 Desktop UI (PID: $pid)"
        # 先尝试优雅关闭
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
        sleep 1
        # 如果还在运行，强制杀掉
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$UI_PID_FILE"
    fi

    cleanup_port "$UI_PORT" "Desktop UI / Vite"

    # 停止 Core Engine
    if is_running "$CORE_PID_FILE"; then
        local pid=$(cat "$CORE_PID_FILE")
        log_info "停止 Core Engine (PID: $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 1
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$CORE_PID_FILE"
    fi

    cleanup_port "$CORE_PORT" "Core Engine"

    # 停止 AI Sidecar
    if is_running "$SIDECAR_PID_FILE"; then
        local pid=$(cat "$SIDECAR_PID_FILE")
        log_info "停止 AI Sidecar (PID: $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 1
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$SIDECAR_PID_FILE"
    fi

    # 停止 Model API Server
    if is_running "$MODEL_API_PID_FILE"; then
        local pid=$(cat "$MODEL_API_PID_FILE")
        log_info "停止 Model API Server (PID: $pid)"
        kill "$pid" 2>/dev/null || true
        sleep 1
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$MODEL_API_PID_FILE"
    fi

    cleanup_port "$MODEL_API_PORT" "Model API"

    log_success "所有服务已停止"
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        log_error "未找到 python3，请先安装 Python 3.11+"
        exit 1
    fi

    # 检查 Rust
    if ! command -v cargo &> /dev/null; then
        log_error "未找到 cargo，请先安装 Rust"
        exit 1
    fi

    # 检查 Node.js
    if ! command -v node &> /dev/null; then
        log_error "未找到 node，请先安装 Node.js 18+"
        exit 1
    fi

    log_success "依赖检查通过"
}

# 启动 AI Sidecar
start_sidecar() {
    log_info "启动 AI Sidecar..."

    cd "$PROJECT_ROOT/ai-sidecar"

    # 检查虚拟环境
    if [ ! -d ".venv" ]; then
        log_warn "虚拟环境不存在，正在创建..."
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt
    else
        source .venv/bin/activate
    fi

    # 启动 Sidecar（后台运行）
    nohup python main.py > "$SIDECAR_LOG" 2>&1 &
    echo $! > "$SIDECAR_PID_FILE"

    # 启动 Model API Server（后台运行）
    nohup python model_api_server.py > "$MODEL_API_LOG" 2>&1 &
    echo $! > "$MODEL_API_PID_FILE"

    log_success "AI Sidecar 已启动 (PID: $(cat $SIDECAR_PID_FILE))"
    log_success "Model API Server 已启动 (PID: $(cat $MODEL_API_PID_FILE))"
    log_info "日志文件: $SIDECAR_LOG"

    # 等待 Sidecar 启动
    log_info "等待 AI Sidecar 初始化..."
    sleep 3
}

# 启动 Core Engine
start_core() {
    log_info "启动 Core Engine..."

    cd "$PROJECT_ROOT/core-engine"

    # 构建（如果需要）
    if [ ! -f "target/release/memory-bread" ]; then
        log_info "首次运行，正在构建 Core Engine..."
        cargo build --release
    fi

    # 启动 Core Engine（后台运行）
    nohup ./target/release/memory-bread > "$CORE_LOG" 2>&1 &
    echo $! > "$CORE_PID_FILE"

    log_success "Core Engine 已启动 (PID: $(cat "$CORE_PID_FILE"))"
    log_info "日志文件: $CORE_LOG"

    # 等待 Core Engine 启动
    log_info "等待 Core Engine 初始化..."
    sleep 3

    wait_for_http "http://localhost:${CORE_PORT}/health" "Core Engine"
}

# 启动 Desktop UI
start_ui() {
    log_info "启动 Desktop UI..."

    cd "$PROJECT_ROOT/desktop-ui"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        log_warn "node_modules 不存在，正在安装依赖..."
        npm install
    fi

    # 确保 Rust 在 PATH 中
    export PATH="$HOME/.cargo/bin:$PATH"

    # 启动 Tauri 开发服务器（后台运行）
    log_info "启动 Tauri 开发服务器..."
    nohup npm run tauri:dev > "$UI_LOG" 2>&1 &
    echo $! > "$UI_PID_FILE"

    log_success "Desktop UI 已启动 (PID: $(cat "$UI_PID_FILE"))"
    log_info "日志文件: $UI_LOG"
    log_info "等待 Desktop UI 初始化..."
    sleep 5

    if curl -fsS "http://localhost:${UI_PORT}" > /dev/null 2>&1; then
        log_success "Desktop UI / Vite 健康检查通过"
    else
        log_warn "Desktop UI / Vite 健康检查失败，请查看日志"
    fi
}

# 主函数
main() {
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║     记忆面包 启动脚本 v1.0           ║"
    echo "╚════════════════════════════════════════╝"
    echo ""

    # 解析命令行参数
    case "${1:-start}" in
        start)
            # 检查是否已经在运行
            if is_running "$SIDECAR_PID_FILE" || is_running "$CORE_PID_FILE" || is_running "$UI_PID_FILE"; then
                log_warn "检测到现有组件仍在运行，先执行全组件 stop 以避免脏状态..."
                stop_all
                sleep 2
            fi

            check_dependencies
            start_sidecar
            start_core
            start_ui
            show_status
            ;;
        stop)
            stop_all
            ;;
        restart)
            log_info "执行全组件 restart（AI Sidecar → Core Engine → Desktop UI）..."
            stop_all
            sleep 2
            check_dependencies
            start_sidecar
            start_core
            start_ui
            show_status
            log_info "联调测试前请优先使用 ./start.sh restart，避免旧进程状态污染测试结果"
            ;;
        status)
            show_status
            ;;
        logs)
            log_info "查看日志 (Ctrl+C 退出)..."
            tail -f "$SIDECAR_LOG" "$CORE_LOG" "$UI_LOG" 2>/dev/null
            ;;
        *)
            echo "用法: $0 {start|stop|restart|status|logs}"
            echo ""
            echo "命令说明:"
            echo "  start   - 启动所有服务"
            echo "  stop    - 停止所有服务"
            echo "  restart - 重启所有服务"
            echo "  status  - 查看服务状态"
            echo "  logs    - 查看实时日志"
            exit 1
            ;;
    esac
}

# 捕获 Ctrl+C 信号
trap 'echo ""; log_info "收到中断信号，正在停止服务..."; stop_all; exit 0' INT TERM

# 执行主函数
main "$@"

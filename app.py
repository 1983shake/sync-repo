# ============================================================================
# 最小化 Python 示例应用
# 用途：验证 Docker 镜像构建流水线是否正常工作
#
# 暴露三个端点：
#   GET /          -> 返回欢迎信息
#   GET /health    -> 健康检查（供 Docker HEALTHCHECK / K8s 探针使用）
#   GET /version   -> 返回构建时注入的版本号（验证 --build-arg 是否生效）
# ============================================================================
import os
import sys
import signal
import logging
from flask import Flask, jsonify

# ----------------------------- 配置 -----------------------------
# ⚠️ 可修改：通过环境变量覆盖端口（默认 8000）
PORT = int(os.environ.get("PORT", "8000"))
# ⚠️ 可修改：通过环境变量覆盖日志级别（默认 INFO）
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
# 版本号由 Dockerfile 中的 ARG 注入为环境变量
APP_VERSION = os.environ.get("APP_VERSION", "unknown")

# ----------------------------- 日志 -----------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ----------------------------- 应用 -----------------------------
app = Flask(__name__)


@app.route("/")
def index():
    """根路径：返回欢迎信息。"""
    return jsonify(
        {
            "message": "Hello from Python Docker image!",
            "version": APP_VERSION,
        }
    )


@app.route("/health")
def health():
    """健康检查：容器运行正常时返回 200。"""
    return jsonify({"status": "ok"}), 200


@app.route("/version")
def version():
    """版本信息：验证构建时注入的版本号。"""
    return jsonify(
        {
            "version": APP_VERSION,
            "python": sys.version.split()[0],
        }
    )


# ----------------------------- 优雅退出 -----------------------------
def _shutdown(signum, frame):
    """收到 SIGTERM / SIGINT 时优雅退出。"""
    logger.info("收到信号 %s，正在关闭服务...", signum)
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


# ----------------------------- 启动 -----------------------------
if __name__ == "__main__":
    logger.info("启动服务，端口=%d，版本=%s", PORT, APP_VERSION)
    # 监听 0.0.0.0 以允许容器外部访问
    app.run(host="0.0.0.0", port=PORT, debug=False)

# ============================================================================
# 最小化 Python 应用 Dockerfile
#   覆盖测试点：
#     1. 多阶段构建（构建阶段 + 运行阶段）
#     2. pip 依赖安装
#     3. 构建参数（--build-arg）注入版本号
#     4. 非 root 用户运行
#     5. 健康检查（HEALTHCHECK）
#     6. 优雅退出（通过 SIGTERM 信号）
# ============================================================================

# ----------------------------- 构建阶段 -----------------------------
# ⚠️ 可修改：根据项目要求调整 Python 版本（如 python:3.11-slim）
FROM python:3.12-slim AS builder

WORKDIR /build

# 复制依赖清单，利用 Docker 层缓存
COPY requirements.txt ./

# 安装依赖到独立目录（便于后续拷贝到运行阶段）
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ----------------------------- 运行阶段 -----------------------------
FROM python:3.12-slim AS runtime

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# 从构建阶段拷贝已安装的依赖
COPY --from=builder /install /usr/local

# 创建非 root 用户
RUN useradd -m -u 1000 appuser

# 拷贝应用源码
COPY --chown=appuser:appuser app.py ./

# 切换到非 root 用户
USER appuser

# 声明构建参数：版本号从外部注入
# ⚠️ 说明：CNB 流水线目前使用 docker build 未传 --build-arg，
#         如需注入版本号，可修改 .cnb.yml 中 docker build 命令添加：
#         --build-arg APP_VERSION=${VERSION}
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# ⚠️ 需要修改：改为你的应用实际监听端口（默认 8000）
EXPOSE 8000

# 健康检查：每 30 秒探测一次 /health 端点
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# 启动命令（使用 exec 形式，确保 Python 进程能直接收到 SIGTERM）
CMD ["python", "app.py"]
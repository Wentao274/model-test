# =============================================================================
# 大模型推理能力测试框架 Docker 镜像
# =============================================================================
# 构建命令: docker build -t model-test .
# 运行命令: docker run --rm -it model-test
# 或带参数:  docker run --rm -it model-test pytest -m p0 -v
# =============================================================================

FROM python:3.10-slim

# 防止交互式安装时询问
ENV DEBIAN_FRONTEND=noninteractive

# =============================================================================
# 1. 安装系统依赖和 uv
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (极快的 Python 包管理工具)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# 2. 设置工作目录
# =============================================================================
WORKDIR /app

# =============================================================================
# 3. 复制项目文件 (排除 logs 和 test_reports)
# =============================================================================
# 复制所有必需文件
COPY requirements.txt ./
COPY pytest.ini ./
COPY config.yaml ./
COPY conftest.py ./
COPY checkpoints.md ./
COPY README.md ./
COPY "主流模型推理功能测试点矩阵.md" ./

# 复制目录
COPY base/ ./base/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY fixtures/ ./fixtures/

# =============================================================================
# 4. 使用 uv 安装 Python 依赖
# =============================================================================
# 创建虚拟环境
RUN uv venv /app/.venv

# 激活虚拟环境并安装依赖
RUN . /app/.venv/bin/activate && \
    uv pip install --no-cache -r requirements.txt

# =============================================================================
# 5. 设置环境变量
# =============================================================================
# 激活虚拟环境
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Python 环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# =============================================================================
# 6. 健康检查
# =============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import pytest; print('Health check passed')" || exit 1

# =============================================================================
# 7. 默认入口点
# =============================================================================
# 默认运行 pytest -v
# 可以通过 docker run 覆盖命令，如: docker run model-test pytest -m p0 -v
ENTRYPOINT ["/app/.venv/bin/python", "-m", "pytest"]
CMD ["-v"]
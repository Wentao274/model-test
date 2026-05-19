# =============================================================================
# 大模型推理能力测试框架 Docker 镜像
# =============================================================================
# 构建命令: docker build -t model-test .
# 运行命令: docker run -v /path/to/maas:/maas -e DOCKER_BASE_URL=... model-test pytest -v
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
    vim \
    less \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (极快的 Python 包管理工具)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# 2. 安装 Python 依赖到系统
# =============================================================================
RUN uv pip install --system --no-cache \
    pytest \
    pytest-timeout \
    pyyaml \
    requests

# =============================================================================
# 3. 创建入口点脚本
# =============================================================================
RUN echo '#!/bin/bash\
\
echo "=== 大模型推理能力测试框架 ===";\
echo "";\
\
if [ ! -d "/maas/model-test" ]; then\
    echo "错误: /maas/model-test 目录不存在";\
    echo "请确保挂载了包含测试框架代码的目录到 /maas";\
    exit 1;\
fi;\
\
if [ ! -f "/maas/model-test/conftest.py" ]; then\
    echo "错误: /maas/model-test/conftest.py 不存在";\
    echo "请确保挂载了正确的测试框架目录";\
    exit 1;\
fi;\
\
if [ -f "/maas/model-test/requirements.txt" ]; then\
    echo "检测到 requirements.txt，正在安装依赖...";\
    uv pip install --system --no-cache -r /maas/model-test/requirements.txt;\
fi;\
\
echo "开始执行测试...";\
echo "";\
\
exec python -m pytest "$@"' > /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["pytest", "-v"]
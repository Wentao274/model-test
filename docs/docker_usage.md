# Docker 运行示例配置
# 使用前请根据实际情况修改

# 使用方式 (二选一):
# 1. 直接使用环境变量:
#    docker run --rm -it \
#      -e DOCKER_BASE_URL=http://127.0.0.1:8080/v1 \
#      -e DOCKER_API_KEY=your-api-key \
#      -e DOCKER_MODEL_NAME=glm5 \
#      model-test pytest -v

# 2. 使用 run_docker.sh 脚本:
#    ./run_docker.sh run --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5

# =============================================================================
# 环境变量说明
# =============================================================================
# DOCKER_CHIP          - 芯片平台名称 (用于日志/报告目录命名)
# DOCKER_BASE_URL      - API 基础地址 (必需)
# DOCKER_API_KEY       - API 密钥 (必需)
# DOCKER_MODEL_NAME    - 模型名称 (如 glm5, minimax-m2.5)
# DOCKER_THINKING_MODE - 是否启用思考模式 (true/false, 默认 false)
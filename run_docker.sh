#!/bin/bash
# =============================================================================
# Docker 构建与运行脚本
# 
# Volume 映射: /data/lwt/maas -> /maas
# 工作目录: /maas/model-test
# =============================================================================

set -e

IMAGE_NAME="model-test"
CONTAINER_NAME="model-test-runner"

# Volume 映射配置
HOST_MAAS_DIR="/data/lwt/maas"
CONTAINER_MAAS_DIR="/maas"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== 大模型推理能力测试框架 Docker 脚本 ===${NC}"

show_help() {
    echo "用法: $0 [命令] [Docker参数] -- [pytest参数]"
    echo ""
    echo "命令:"
    echo "  build          构建 Docker 镜像"
    echo "  run            运行测试 (默认)"
    echo "  shell          启动交互式 Shell"
    echo "  help           显示帮助"
    echo ""
    echo "Docker 参数:"
    echo "  --chip NAME              芯片平台名称"
    echo "  --base-url URL           API 基础地址"
    echo "  --api-key KEY            API 密钥"
    echo "  --model-name NAME        模型名称"
    echo "  --thinking-mode          启用思考模式"
    echo ""
    echo "Volume 映射:"
    echo "  ${HOST_MAAS_DIR} -> ${CONTAINER_MAAS_DIR}"
    echo ""
    echo "示例:"
    echo "  $0 build"
    echo "  $0 run --chip NVIDIA-H100 --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5"
    echo "  $0 run --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5 -m p0 -v"
    echo "  $0 shell"
}

build() {
    echo -e "${GREEN}构建镜像: ${IMAGE_NAME}${NC}"
    docker build -t ${IMAGE_NAME} .
    echo -e "${GREEN}✓ 完成${NC}"
}

run() {
    local docker_args=""
    local pytest_args=""
    local dash_found=false
    
    # 解析参数
    for arg in "$@"; do
        if [[ "$arg" == "--" ]]; then
            dash_found=true
            continue
        fi
        
        if [[ "$dash_found" == "false" ]]; then
            # Docker 参数
            case "$arg" in
                --chip|--base-url|--api-key|--model-name)
                    docker_args="$docker_args $arg"
                    ;;
                --thinking-mode)
                    docker_args="$docker_args $arg"
                    ;;
                *)
                    # 未知参数，可能是值
                    docker_args="$docker_args $arg"
                    ;;
            esac
        else
            # pytest 参数
            pytest_args="$pytest_args $arg"
        fi
    done
    
    # 检查是否有 Docker 参数
    if [[ -z "$docker_args" ]]; then
        echo -e "${YELLOW}注意: 未指定 Docker 参数，使用 config.yaml${NC}"
        docker run --rm -it \
            -v ${HOST_MAAS_DIR}:${CONTAINER_MAAS_DIR} \
            --name ${CONTAINER_NAME} \
            ${IMAGE_NAME} ${pytest_args:-"-v"}
        return
    fi
    
    echo -e "${GREEN}使用 Docker 模式运行${NC}"
    
    # 提取参数值
    local chip=""
    local base_url=""
    local api_key=""
    local model_name=""
    local thinking_mode="false"
    
    local prev_arg=""
    for arg in $docker_args; do
        case "$prev_arg" in
            --chip) chip="$arg" ;;
            --base-url) base_url="$arg" ;;
            --api-key) api_key="$arg" ;;
            --model-name) model_name="$arg" ;;
        esac
        case "$arg" in
            --thinking-mode) thinking_mode="true" ;;
        esac
        prev_arg="$arg"
    done
    
    echo -e "${BLUE}配置:${NC}"
    [[ -n "$chip" ]] && echo "  chip: $chip"
    [[ -n "$base_url" ]] && echo "  base_url: $base_url"
    [[ -n "$api_key" ]] && echo "  api_key: ***"
    [[ -n "$model_name" ]] && echo "  model_name: $model_name"
    [[ "$thinking_mode" == "true" ]] && echo "  thinking_mode: true"
    echo "  volume: ${HOST_MAAS_DIR} -> ${CONTAINER_MAAS_DIR}"
    echo ""
    
    # 构建命令
    local cmd="docker run --rm -it"
    cmd="$cmd -v ${HOST_MAAS_DIR}:${CONTAINER_MAAS_DIR}"
    [[ -n "$chip" ]] && cmd="$cmd -e DOCKER_CHIP=$chip"
    [[ -n "$base_url" ]] && cmd="$cmd -e DOCKER_BASE_URL=$base_url"
    [[ -n "$api_key" ]] && cmd="$cmd -e DOCKER_API_KEY=$api_key"
    [[ -n "$model_name" ]] && cmd="$cmd -e DOCKER_MODEL_NAME=$model_name"
    [[ "$thinking_mode" == "true" ]] && cmd="$cmd -e DOCKER_THINKING_MODE=true"
    cmd="$cmd --name ${CONTAINER_NAME} ${IMAGE_NAME}"
    
    # 添加 pytest 参数
    if [[ -n "$pytest_args" ]]; then
        cmd="$cmd $pytest_args"
    else
        cmd="$cmd -v"
    fi
    
    echo -e "${GREEN}执行: pytest${NC}"
    eval $cmd
}

shell() {
    echo -e "${GREEN}启动交互式 Shell${NC}"
    docker run --rm -it \
        -v ${HOST_MAAS_DIR}:${CONTAINER_MAAS_DIR} \
        --entrypoint /bin/bash \
        ${IMAGE_NAME}
}

case "${1:-help}" in
    build) build ;;
    run) shift; run "$@" ;;
    shell) shell ;;
    help|--help|-h) show_help ;;
    *) echo -e "${RED}未知命令: $1${NC}"; show_help; exit 1 ;;
esac
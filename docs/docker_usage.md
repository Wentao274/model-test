# Docker 使用说明

## Volume 映射

容器启动时需要将宿主机目录挂载到容器：

| 宿主机路径 | 容器路径 | 说明 |
|-----------|---------|------|
| `/data/lwt/maas` | `/maas` | 宿主机目录，需包含 `model-test/` 子目录 |

容器工作目录：`/maas/model-test`

## 目录结构要求

宿主机目录结构：
```
/data/lwt/maas/
└── model-test/        # 测试框架代码
    ├── tests/
    ├── base/
    ├── conftest.py
    ├── config.yaml
    ├── requirements.txt
    └── ...
```

## 环境变量

| 变量名 | 说明 | 必需 |
|-------|------|-----|
| `DOCKER_BASE_URL` | API 基础地址 | 是 |
| `DOCKER_API_KEY` | API 密钥 | 是 |
| `DOCKER_MODEL_NAME` | 模型名称 (如 glm5, minimax-m2.5) | 否 |
| `DOCKER_CHIP` | 芯片平台名称 (用于日志目录) | 否 |
| `DOCKER_THINKING_MODE` | 是否启用思考模式 (true/false) | 否 |

## 使用方式

### 方式 1：使用 run_docker.sh 脚本（推荐）

```bash
# 构建镜像
./run_docker.sh build

# 运行测试
./run_docker.sh run --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5

# 运行 P0 测试
./run_docker.sh run --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5 -m p0 -v

# 启用思考模式
./run_docker.sh run --base-url http://127.0.0.1:8080/v1 --api-key abc123 --model-name glm5 --thinking-mode

# 进入交互式 Shell
./run_docker.sh shell
```

### 方式 2：直接使用 docker run

```bash
# 构建镜像
docker build -t model-test .

# 运行测试（必需参数）
docker run -it \
  -v /data/lwt/maas:/maas \
  -e DOCKER_BASE_URL=http://127.0.0.1:8080/v1 \
  -e DOCKER_API_KEY=your-api-key \
  -e DOCKER_MODEL_NAME=glm5 \
  model-test pytest -v

# 运行 P0 测试
docker run -it \
  -v /data/lwt/maas:/maas \
  -e DOCKER_BASE_URL=http://127.0.0.1:8080/v1 \
  -e DOCKER_API_KEY=your-api-key \
  -e DOCKER_MODEL_NAME=glm5 \
  model-test pytest -m p0 -v

# 启用思考模式
docker run -it \
  -v /data/lwt/maas:/maas \
  -e DOCKER_BASE_URL=http://127.0.0.1:8080/v1 \
  -e DOCKER_API_KEY=your-api-key \
  -e DOCKER_MODEL_NAME=glm5 \
  -e DOCKER_THINKING_MODE=true \
  model-test pytest -m p0 -v

# 进入交互式 Shell
docker run -it \
  -v /data/lwt/maas:/maas \
  --entrypoint /bin/bash \
  model-test
```

## 注意事项

1. **Volume 映射**：`/data/lwt/maas` 目录必须在宿主机上存在，且包含 `model-test/` 子目录
2. **依赖安装**：容器启动时会自动检测并安装 `requirements.txt` 中的依赖
3. **环境变量优先级**：环境变量 > 命令行参数 > config.yaml
4. **思考模式**：默认关闭，使用 `--thinking-mode` 或 `DOCKER_THINKING_MODE=true` 启用
5. **代码不打包**：镜像不包含测试代码，依赖 volume 挂载运行最新代码
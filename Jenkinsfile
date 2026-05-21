pipeline {
    agent any

    parameters {
        string(name: 'CHIP', defaultValue: 'nvidia-h100', description: '芯片平台名称')
        string(name: 'MODEL', defaultValue: 'kimi-k2.5', description: '模型名称')
        string(name: 'BASE_URL', defaultValue: 'http://10.201.149.10:8080/v1', description: 'API 地址')
        booleanParam(name: 'THINKING_MODE', defaultValue: true, description: '启用思考模式')
        string(name: 'MARKER', defaultValue: 'j_response_quality', description: '测试标记 (p0, p1, smoke 等)')
        string(name: 'WORK_DIR', defaultValue: '/root/liwt/maas-image/model-test', description: '宿主机测试目录')
        text(name: 'RECIPIENTS', defaultValue: 'liwt@zetyun.com', description: '邮件接收者（逗号分隔）')
    }

    environment {
        SSH_CREDENTIALS = 'HOST_SSH_KEY'
        API_KEY_CREDENTIALS = 'API_KEY'
        REMOTE_HOST = '10.201.132.50'
        REMOTE_USER = 'root'
        BUILD_OUTPUT_DIR = "builds/${BUILD_NUMBER}"
    }

    stages {
        stage('环境检查') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh '''
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
echo "工作目录: $(pwd)"
ls -la

# 恢复工作区并拉取最新代码
echo "=== 同步代码 ==="
export https_proxy=http://100.64.1.68:1080
export http_proxy=http://100.64.1.68:1080
git restore .
git pull
unset https_proxy
unset http_proxy

echo "=== 设置权限 ==="
chmod -R 755 ./*
if [ ! -d "${params.WORK_DIR}/.venv" ]; then
    echo "创建虚拟环境..."
    cd ${params.WORK_DIR}
    uv venv
fi
cd ${params.WORK_DIR}
source .venv/bin/activate
uv pip install -r requirements.txt
ENDSSH'''
                }
            }
        }

        stage('运行测试') {
            steps {
                script {
                    withCredentials([string(credentialsId: "${API_KEY_CREDENTIALS}", variable: 'API_KEY')]) {
                        sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                            catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                                sh '''
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
source .venv/bin/activate
mkdir -p ${BUILD_OUTPUT_DIR}
THINKING_ARG=""
if [ "${params.THINKING_MODE}" = "true" ]; then
    THINKING_ARG="--thinking-mode"
fi

pytest tests/test_j_response_quality.py::TestResponseQuality::test_response_specificity_check -v \
    --base-url "${params.BASE_URL}" \
    --api-key "${API_KEY}" \
    --model-name "${params.MODEL}" \
    --chip "${params.CHIP}" \
    --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \
    --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \
    $THINKING_ARG
ENDSSH'''
                            }
                        }
                    }
                }
            }
        }

        stage('生成Allure报告') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh '''
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
cd ${params.WORK_DIR}
# 生成 Allure HTML 报告
if [ -d "${BUILD_OUTPUT_DIR}/allure-results" ] && [ "$(ls -A ${BUILD_OUTPUT_DIR}/allure-results 2>/dev/null)" ]; then
    echo "生成 Allure HTML 报告..."
    allure generate "${BUILD_OUTPUT_DIR}/allure-results" -o "${BUILD_OUTPUT_DIR}/allure-html" --clean
    echo "Allure HTML 报告已生成: ${BUILD_OUTPUT_DIR}/allure-html"
else
    echo "警告: allure-results 目录不存在或为空"
fi
ENDSSH'''
                }
            }
        }

        stage('拉取报告到Jenkins') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        sh '''
mkdir -p reports/${BUILD_NUMBER}

# 拉取 Markdown 汇总报告
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "find ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-report -name '*.md' -exec cp {} ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/ \\; 2>/dev/null || true"
scp -o StrictHostKeyChecking=no \
    ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/*.md \
    ./reports/${BUILD_NUMBER}/ 2>/dev/null || echo "未找到汇总报告"

# 拉取 allure-results（用于 Jenkins Allure 插件）
if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-results ]"; then
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "cd ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} && tar -czvf allure-results.tar.gz allure-results"
    scp -o StrictHostKeyChecking=no \
        ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-results.tar.gz \
        ./reports/${BUILD_NUMBER}/
    tar -xzf ./reports/${BUILD_NUMBER}/allure-results.tar.gz -C ./reports/${BUILD_NUMBER}/
fi

# 拉取 Allure HTML 报告
if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html ]"; then
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "cd ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} && tar -czvf allure-html.tar.gz allure-html"
    scp -o StrictHostKeyChecking=no \
        ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html.tar.gz \
        ./reports/${BUILD_NUMBER}/
    
    mkdir -p reports/${BUILD_NUMBER}/allure-html
    tar -xzf ./reports/${BUILD_NUMBER}/allure-html.tar.gz -C ./reports/${BUILD_NUMBER}/
fi
'''
                    }
                }
            }
        }

        stage('发送邮件') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    script {
                        def emailBody = """
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background-color: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .header { background-color: ${currentBuild.currentResult == 'SUCCESS' ? '#4CAF50' : '#f44336'}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }
        .content { padding: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #f2f2f2; width: 30%; }
        .footer { margin-top: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 0 0 5px 5px; color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">模型推理功能测试报告 - 构建 #${BUILD_NUMBER}</h2>
        </div>
        <div class="content">
            <h3>测试概要</h3>
            <table>
                <tr><th>构建编号</th><td>#${BUILD_NUMBER}</td></tr>
                <tr><th>芯片平台</th><td>${params.CHIP}</td></tr>
                <tr><th>模型名称</th><td>${params.MODEL}</td></tr>
                <tr><th>测试标记</th><td>${params.MARKER}</td></tr>
                <tr><th>执行时间</th><td>${currentBuild.durationString}</td></tr>
                <tr><th>构建状态</th><td>${currentBuild.currentResult}</td></tr>
            </table>
            
            <p style="margin-top: 20px;">详细测试报告请查看附件中的 Markdown 文件。</p>
            <p>Jenkins 构建地址: <a href="${env.BUILD_URL}">${env.BUILD_URL}</a></p>
        </div>
        <div class="footer">
            此邮件由 Jenkins 自动发送，请勿回复。
        </div>
    </div>
</body>
</html>"""
                        
                        emailext(
                            subject: "[测试报告] ${params.CHIP} - ${params.MODEL} - 构建 #${BUILD_NUMBER} - ${currentBuild.currentResult}",
                            body: emailBody,
                            to: "${params.RECIPIENTS}",
                            attachmentsPattern: "reports/${BUILD_NUMBER}/*.md",
                            mimeType: 'text/html'
                        )
                    }
                }
            }
        }

        stage('清理旧构建') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh '''
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
cd ${params.WORK_DIR}/builds 2>/dev/null || exit 0
ls -t | tail -n +21 | xargs -r rm -rf
ENDSSH'''
                }
            }
        }
    }

    post {
        always {
            script {
                archiveArtifacts artifacts: "reports/${env.BUILD_NUMBER}/**", allowEmptyArchive: true, fingerprint: true
                try {
                    allure includeProperties: false,
                           jdk: '',
                           results: [[path: "reports/${env.BUILD_NUMBER}/allure-results"]]
                } catch (Exception e) {
                    echo "Allure 报告生成失败: ${e.message}"
                }
            }
        }
        cleanup {
            cleanWs()
        }
    }
}
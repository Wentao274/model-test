pipeline {
    agent any

    parameters {
        string(name: 'TESTER', defaultValue: 'liwt', description: '测试人员名称（必填）')
        string(name: 'CHIP', defaultValue: 'nvidia-h100', description: '芯片平台名称（必填）')
        choice(name: 'ENGINE', choices: ['vllm', 'sglang'], description: '推理框架（必填）')
        choice(name: 'PD', choices: ['agg', 'disagg'], description: 'PD分离模式（agg表示非PD分离，disagg表示PD分离）')
        string(name: 'MODEL', defaultValue: 'kimi-k2.5', description: '模型服务名称 (必填)')
        string(name: 'BASE_URL', defaultValue: 'http://10.201.149.10:8080', description: 'API 地址（必填）')
        password(name: 'API_KEY', defaultValue: '', description: 'API Key (可选，无需认证时留空)')
        booleanParam(name: 'THINKING_MODE', defaultValue: true, description: '启用思考模式')
        choice(name: 'MARKER', choices: ['all', 'a_basic', 'b_advanced', 'c_multimodal', 'd_long_context', 'e_performance', 'f_stability', 'g_api', 'h_quality_chat_completions', 'i_quality_completions', 'p0', 'p1', 'p2', 'slow', 'smoke'], description: '测试标记，选择要执行的测试标记类型')
        text(name: 'RECIPIENTS', defaultValue: 'liwt@zetyun.com', description: '测试报告邮件接收者（逗号分隔）')
        string(name: 'WORK_DIR', defaultValue: '/dingofs/data2/userdata/liwt/maas-image/model-test', description: '测试仓库目录，请不要改动')
    }

    environment {
        SSH_CREDENTIALS = 'HOST_SSH_KEY'
        REMOTE_HOST = '10.201.132.50'
        REMOTE_USER = 'root'
        BUILD_OUTPUT_DIR = "builds/${params.TESTER}/${BUILD_NUMBER}"
    }

    stages {
        stage('打印测试参数') {
            steps {
                script {
                    println("========================================")
                    println("=== 测试参数信息 ===")
                    println("========================================")
                    println("测试人员:     ${params.TESTER}")
                    println("芯片平台:     ${params.CHIP}")
                    println("推理框架:     ${params.ENGINE}")
                    println("PD分离模式:   ${params.PD}")
                    println("模型服务名称: ${params.MODEL}")
                    println("BASE_URL:     ${params.BASE_URL}")
                    println("思考模式:     ${params.THINKING_MODE}")
                    println("测试标记:     ${params.MARKER}")
                    println("邮件接收者:   ${params.RECIPIENTS}")
                    println("工作目录:     ${params.WORK_DIR}")
                    println("构建编号:     #${BUILD_NUMBER}")
                    println("========================================")
                }
            }
        }

        stage('环境检查') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << ENDSSH
set -e
cd ${params.WORK_DIR}
echo "工作目录: \$(pwd)"
ls -la

# 恢复工作区并拉取最新代码
echo "=== 同步代码 ==="
export https_proxy=http://100.64.1.68:1080
export http_proxy=http://100.64.1.68:1080
git restore .
git pull
unset https_proxy
unset http_proxy

#echo "=== 设置权限 ==="
#chmod -R 755 ./*
if [ ! -d "${params.WORK_DIR}/.venv" ]; then
    echo "创建虚拟环境..."
    cd ${params.WORK_DIR}
    uv venv
fi
cd ${params.WORK_DIR}
source .venv/bin/activate
uv pip install -r requirements.txt
ENDSSH"""
                }
            }
        }

        stage('运行测试') {
            steps {
                script {
                    def apiKey = params.API_KEY ? params.API_KEY.toString().trim() : ''
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << ENDSSH
set -e
cd ${params.WORK_DIR}
source .venv/bin/activate
mkdir -p ${BUILD_OUTPUT_DIR}

# 清理上一次可能残留的连通性检查失败标记
rm -f ${BUILD_OUTPUT_DIR}/.connectivity_check_failed

if [ "${params.THINKING_MODE}" = "true" ]; then
    if [ "${params.MARKER}" = "all" ] || [ "${params.MARKER}" = "" ]; then
        export CONNECTIVITY_FAILED_FLAG="${BUILD_OUTPUT_DIR}/.connectivity_check_failed"
        pytest -v \\
            --base-url "${params.BASE_URL}" \\
            --api-key "${apiKey}" \\
            --model-name "${params.MODEL}" \\
            --chip "${params.CHIP}" \\
            --engine "${params.ENGINE}" \\
            --pd-mode "${params.PD}" \\
            --tester "${params.TESTER}" \\
            --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \\
            --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \\
            --thinking-mode
    else
        export CONNECTIVITY_FAILED_FLAG="${BUILD_OUTPUT_DIR}/.connectivity_check_failed"
        pytest -v -m "${params.MARKER}" \\
            --base-url "${params.BASE_URL}" \\
            --api-key "${apiKey}" \\
            --model-name "${params.MODEL}" \\
            --chip "${params.CHIP}" \\
            --engine "${params.ENGINE}" \\
            --pd-mode "${params.PD}" \\
            --tester "${params.TESTER}" \\
            --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \\
            --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \\
            --thinking-mode
    fi
else
    if [ "${params.MARKER}" = "all" ] || [ "${params.MARKER}" = "" ]; then
        export CONNECTIVITY_FAILED_FLAG="${BUILD_OUTPUT_DIR}/.connectivity_check_failed"
        pytest -v \\
            --base-url "${params.BASE_URL}" \\
            --api-key "${apiKey}" \\
            --model-name "${params.MODEL}" \\
            --chip "${params.CHIP}" \\
            --engine "${params.ENGINE}" \\
            --pd-mode "${params.PD}" \\
            --tester "${params.TESTER}" \\
            --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \\
            --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \\
            --no-thinking-mode
    else
        export CONNECTIVITY_FAILED_FLAG="${BUILD_OUTPUT_DIR}/.connectivity_check_failed"
        pytest -v -m "${params.MARKER}" \\
            --base-url "${params.BASE_URL}" \\
            --api-key "${apiKey}" \\
            --model-name "${params.MODEL}" \\
            --chip "${params.CHIP}" \\
            --engine "${params.ENGINE}" \\
            --pd-mode "${params.PD}" \\
            --tester "${params.TESTER}" \\
            --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \\
            --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \\
            --no-thinking-mode
    fi
fi
ENDSSH"""
                        }
                    }
                }
            }
        }

        stage('生成Allure报告') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << ENDSSH
set -e
cd ${params.WORK_DIR}
# 生成 Allure HTML 报告
if [ -d "${BUILD_OUTPUT_DIR}/allure-results" ] && [ "\$(ls -A ${BUILD_OUTPUT_DIR}/allure-results 2>/dev/null)" ]; then
    echo "生成 Allure HTML 报告..."
    allure generate "${BUILD_OUTPUT_DIR}/allure-results" -o "${BUILD_OUTPUT_DIR}/allure-html" --clean
    echo "Allure HTML 报告已生成: ${BUILD_OUTPUT_DIR}/allure-html"
else
    echo "警告: allure-results 目录不存在或为空"
fi
ENDSSH"""
                }
            }
        }

        stage('拉取报告到Jenkins') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        sh """
mkdir -p reports/${BUILD_NUMBER}

# 拉取 Markdown 汇总报告
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "find ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-report -name '*.md' -exec cp {} ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/ \\; 2>/dev/null || true"
scp -o StrictHostKeyChecking=no \\
    ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/*.md \\
    ./reports/${BUILD_NUMBER}/ 2>/dev/null || echo "未找到汇总报告"

# 拉取 allure-results（用于 Jenkins Allure 插件）
if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-results ]"; then
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "cd ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} && tar -czvf allure-results.tar.gz allure-results"
    scp -o StrictHostKeyChecking=no \\
        ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-results.tar.gz \\
        ./reports/${BUILD_NUMBER}/
    tar -xzf ./reports/${BUILD_NUMBER}/allure-results.tar.gz -C ./reports/${BUILD_NUMBER}/
fi

# 拉取 Allure HTML 报告
if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html ]"; then
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "cd ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} && tar -czvf allure-html.tar.gz allure-html"
    scp -o StrictHostKeyChecking=no \\
        ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html.tar.gz \\
        ./reports/${BUILD_NUMBER}/

    mkdir -p reports/${BUILD_NUMBER}/allure-html
    tar -xzf ./reports/${BUILD_NUMBER}/allure-html.tar.gz -C ./reports/${BUILD_NUMBER}/
fi
"""
                    }
                }
            }
        }

        stage('发送邮件') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    script {
                        // Markdown 转 HTML 辅助函数
                        def convertMarkdownTableToHtml = { String mdContent ->
                            def html = '<table>'
                            def lines = mdContent.trim().split('\n')
                            def isHeader = true
                            for (line in lines) {
                                line = line.trim()
                                if (!line || line == '|' || line.startsWith('|--')) continue
                                if (line.startsWith('|')) {
                                    line = line.replaceAll(/^\||\|$/, '')
                                    def cells = line.split('\\|').collect { it.trim() }
                                    if (isHeader) {
                                        html += '<thead><tr>'
                                        cells.each { html += "<th>${it}</th>" }
                                        html += '</tr></thead><tbody>'
                                        isHeader = false
                                    } else {
                                        html += '<tr>'
                                        cells.each { html += "<td>${it}</td>" }
                                        html += '</tr>'
                                    }
                                }
                            }
                            html += '</tbody></table>'
                            return html
                        }

                        // 处理模型名中的路径分隔符
                        def modelDisplayName = params.MODEL.contains('/') ? params.MODEL.split('/')[-1] : params.MODEL

                        // 检查 API 连通性是否失败（通过 conftest.py 写入的标记文件）
                        def connectivityCheckFailed = false
                        def connectivityFailureReason = ""
                        try {
                            def flagFile = "${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/.connectivity_check_failed"
                            def flagContent = sh(
                                script: "ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} \"cat ${flagFile} 2>/dev/null\"",
                                returnStdout: true
                            ).trim()
                            if (flagContent) {
                                connectivityCheckFailed = true
                                connectivityFailureReason = flagContent
                            }
                        } catch (Exception e) {
                            echo "检查连通性标记文件失败: ${e.message}"
                        }

                        // 读取 Markdown 报告，提取统计信息
                        def reportFile = sh(script: "ls reports/${BUILD_NUMBER}/*.md 2>/dev/null | head -1", returnStdout: true).trim()
                        def summaryHtml = ""
                        def categoryHtml = ""
                        def conclusionHtml = ""

                        if (reportFile && fileExists(reportFile)) {
                            def content = readFile(reportFile)

                            // 提取统计汇总 section
                            def summaryMatch = content =~ /(?s)## 统计汇总\n(.*?)(?=\n##|\Z)/
                            if (summaryMatch) {
                                def summaryMd = summaryMatch.group(1).trim()
                                summaryHtml = convertMarkdownTableToHtml(summaryMd)
                            }

                            // 提取分类统计 section
                            def categoryMatch = content =~ /(?s)## 分类统计\n(.*?)(?=\n##|\n---|\Z)/
                            if (categoryMatch) {
                                def categoryMd = categoryMatch.group(1).trim()
                                categoryHtml = convertMarkdownTableToHtml(categoryMd)
                            }

                            // 提取测试结论 section
                            def conclusionMatch = content =~ /(?s)## 测试结论\n(.*?)(?=\n##\s+\S|\Z)/
                            if (conclusionMatch) {
                                def conclusionMd = conclusionMatch.group(1).trim()
                                conclusionHtml = conclusionMd
                                    .replaceAll(/>\s*\*\*结论：/, '> <strong>结论：')
                                    .replaceAll(/\*\*/, '</strong>')
                                    .replaceAll(/###\s+(.+)/, '<h4>$1</h4>')
                                    .replaceAll(/(?m)^- ❌\s+(.+)$/, '<div style="color:#d32f2f;padding-left:15px;">❌ $1</div>')
                                    .replaceAll(/(?m)^- ⚠️?\s+(.+)$/, '<div style="color:#f57c00;padding-left:15px;">⚠️ $1</div>')
                                    .replaceAll(/^- ❌/, '<div style="color:#d32f2f;padding-left:15px;">❌ ')
                                    .replaceAll(/^- ⚠️?/, '<div style="color:#f57c00;padding-left:15px;">⚠️ ')
                                    .replaceAll(/(?m)^\*\*(.+?)\*\*[：:](.*)$/, '<strong>$1</strong>$2')
                                    .replaceAll(/\n\n/, '<br/><br/>')
                                    .replaceAll(/\n/, '<br/>')
                            }
                        }

                        // 构建连通性检查失败的提示 HTML（HTML 转义）
                        def connectivityFailureHtml = ""
                        if (connectivityCheckFailed) {
                            def escapedReason = connectivityFailureReason
                                .replace('&', '&amp;')
                                .replace('<', '&lt;')
                                .replace('>', '&gt;')
                                .replace('\n', '<br/>')
                            connectivityFailureHtml = """
    <div style="background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 12px 15px; margin-top: 15px; border-radius: 3px;">
        <h3 style="color: #d32f2f; margin-top: 0; margin-bottom: 8px;">⚠️ 连通性检查未通过</h3>
        <p style="margin-top: 0; margin-bottom: 8px;">本次测试未能正常执行用例，原因是 API 连通性检查失败：</p>
        <pre style="background-color: #fff; padding: 10px; border-radius: 3px; overflow-x: auto; white-space: pre-wrap; margin: 0; font-family: Menlo, Consolas, monospace; font-size: 12px;">${escapedReason}</pre>
    </div>"""
                        }

                        def emailBody = """
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 900px; margin: 0 auto; background-color: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .header { background-color: ${currentBuild.currentResult == 'SUCCESS' ? '#4CAF50' : '#f44336'}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }
        .content { padding: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #f2f2f2; }
        .summary-table th { background-color: #e3f2fd; }
        .category-table th { background-color: #fff3e0; }
        .conclusion { background-color: #f5f5f5; border-left: 4px solid #ff9800; padding: 12px 15px; margin-top: 10px; border-radius: 3px; }
        .conclusion h4 { margin: 8px 0 4px 0; color: #333; }
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
                <tr><th>项目</th><td>值</td></tr>
                <tr><th>构建编号</th><td>#${BUILD_NUMBER}</td></tr>
                <tr><th>测试人员</th><td>${params.TESTER}</td></tr>
                <tr><th>芯片平台</th><td>${params.CHIP}</td></tr>
                <tr><th>推理框架</th><td>${params.ENGINE}</td></tr>
                <tr><th>模型名称</th><td>${modelDisplayName}</td></tr>
                <tr><th>API 地址</th><td>${params.BASE_URL}</td></tr>
                <tr><th>PD模式</th><td>${params.PD}</td></tr>
                <tr><th>测试标记</th><td>${params.MARKER}</td></tr>
                <tr><th>思考模式</th><td>${params.THINKING_MODE}</td></tr>
                <tr><th>执行时间</th><td>${currentBuild.durationString}</td></tr>
                <tr><th>构建状态</th><td>${currentBuild.currentResult}</td></tr>
            </table>
            ${connectivityFailureHtml}

            ${summaryHtml ? "<h3>统计汇总</h3>" + summaryHtml : ""}
            ${categoryHtml ? "<h3>分类统计</h3>" + categoryHtml : ""}
            ${conclusionHtml ? "<h3>测试结论</h3><div class=\"conclusion\">" + conclusionHtml + "</div>" : ""}

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
                            subject: "[模型推理 - 功能测试报告] ${params.CHIP} - ${modelDisplayName} - 构建 #${BUILD_NUMBER} - ${currentBuild.currentResult}",
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
                    sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << ENDSSH
cd ${params.WORK_DIR}/builds/${params.TESTER} 2>/dev/null || exit 0
ls -t | tail -n +21 | xargs -r rm -rf
ENDSSH"""
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
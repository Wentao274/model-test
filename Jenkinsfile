pipeline {
    agent any

    parameters {
        string(name: 'CHIP', defaultValue: 'hygon-bw1000', description: '芯片平台名称')
        string(name: 'MODEL', defaultValue: 'minimax-m2.5', description: '模型名称')
        string(name: 'BASE_URL', defaultValue: 'http://127.0.0.1:8080/v1', description: 'API 地址')
        booleanParam(name: 'THINKING_MODE', defaultValue: false, description: '启用思考模式')
        string(name: 'MARKER', defaultValue: 'p0', description: '测试标记 (p0, p1, smoke 等)')
        string(name: 'WORK_DIR', defaultValue: '/path/to/model-test', description: '宿主机测试目录')
        text(name: 'RECIPIENTS', defaultValue: 'team@example.com', description: '邮件接收者（逗号分隔）')
    }

    environment {
        SSH_CREDENTIALS = 'ssh-credentials-id'
        API_KEY_CREDENTIALS = 'api-key-credentials-id'
        REMOTE_HOST = '192.168.1.100'
        REMOTE_USER = 'root'
        BUILD_OUTPUT_DIR = "builds/${BUILD_NUMBER}"
    }

    stages {
        stage('环境检查') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'EOF'
                            set -e
                            
                            echo "工作目录: ${params.WORK_DIR}"
                            ls -la ${params.WORK_DIR}
                            
                            if [ ! -d "${params.WORK_DIR}/.venv" ]; then
                                echo "创建虚拟环境..."
                                cd ${params.WORK_DIR}
                                uv venv
                            fi
                            
                            cd ${params.WORK_DIR}
                            source .venv/bin/activate
                            uv pip install -r requirements.txt
                        EOF
                    """
                }
            }
        }

        stage('运行测试') {
            steps {
                script {
                    withCredentials([string(credentialsId: "${API_KEY_CREDENTIALS}", variable: 'API_KEY')]) {
                        sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                            sh """
                                ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << EOF
                                    set -e
                                    
                                    cd ${params.WORK_DIR}
                                    source .venv/bin/activate
                                    
                                    # 创建本次构建专用目录
                                    mkdir -p ${BUILD_OUTPUT_DIR}
                                    
                                    THINKING_ARG=""
                                    if [ "${params.THINKING_MODE}" = "true" ]; then
                                        THINKING_ARG="--thinking-mode"
                                    fi
                                    
                                    pytest -v -m ${params.MARKER} \\
                                        --base-url "${params.BASE_URL}" \\
                                        --api-key "${API_KEY}" \\
                                        --model-name "${params.MODEL}" \\
                                        --chip "${params.CHIP}" \\
                                        --alluredir="${BUILD_OUTPUT_DIR}/allure-results" \\
                                        --summary-report-dir="${BUILD_OUTPUT_DIR}/allure-report" \\
                                        \${THINKING_ARG}
                                EOF
                            """
                        }
                    }
                }
            }
        }

        stage('生成Allure报告') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << EOF
                            set -e
                            
                            cd ${params.WORK_DIR}
                            
                            # 生成 Allure HTML 报告
                            if [ -d "${BUILD_OUTPUT_DIR}/allure-results" ] && [ "\$(ls -A ${BUILD_OUTPUT_DIR}/allure-results 2>/dev/null)" ]; then
                                echo "生成 Allure HTML 报告..."
                                allure generate "${BUILD_OUTPUT_DIR}/allure-results" -o "${BUILD_OUTPUT_DIR}/allure-html" --clean
                            else
                                echo "警告: allure-results 目录不存在或为空"
                            fi
                        EOF
                    """
                }
            }
        }

        stage('拉取报告到Jenkins') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
                        mkdir -p reports/${BUILD_NUMBER}
                        
                        # 拉取 Allure 汇总报告 (Markdown)
                        scp -o StrictHostKeyChecking=no \
                            ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-report/*/*.md \
                            ./reports/${BUILD_NUMBER}/ 2>/dev/null || echo "未找到汇总报告"
                        
                        # 拉取 Allure HTML 报告
                        if ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "[ -d ${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html ]"; then
                            ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "cd ${params.WORK_DIR}/${BUILD_OUTPUT_DIR} && tar -czvf allure-html.tar.gz allure-html"
                            scp -o StrictHostKeyChecking=no \
                                ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${BUILD_OUTPUT_DIR}/allure-html.tar.gz \
                                ./reports/${BUILD_NUMBER}/
                            tar -xzf ./reports/${BUILD_NUMBER}/allure-html.tar.gz -C ./reports/${BUILD_NUMBER}/
                        fi
                    """
                }
            }
        }

        stage('发送邮件') {
            steps {
                script {
                    def summaryFile = sh(
                        script: "ls reports/${BUILD_NUMBER}/*.md 2>/dev/null | head -1",
                        returnStdout: true
                    ).trim()
                    
                    def emailBody = """
                        <html>
                        <head>
                            <style>
                                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                                .header { background-color: ${currentBuild.result == 'SUCCESS' ? '#4CAF50' : '#f44336'}; color: white; padding: 15px; border-radius: 5px; }
                                .content { padding: 20px 0; }
                                table { border-collapse: collapse; width: 100%; margin-top: 15px; }
                                th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
                                th { background-color: #f2f2f2; }
                                .footer { margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; color: #666; }
                            </style>
                        </head>
                        <body>
                            <div class="header">
                                <h2>测试报告 - 构建 #${BUILD_NUMBER}</h2>
                            </div>
                            <div class="content">
                                <h3>测试概要</h3>
                                <table>
                                    <tr><th width="30%">项目</th><th>值</th></tr>
                                    <tr><td>构建编号</td><td>#${BUILD_NUMBER}</td></tr>
                                    <tr><td>芯片平台</td><td>${params.CHIP}</td></tr>
                                    <tr><td>模型名称</td><td>${params.MODEL}</td></tr>
                                    <tr><td>测试标记</td><td>${params.MARKER}</td></tr>
                                    <tr><td>执行时间</td><td>${currentBuild.durationString}</td></tr>
                                    <tr><td>构建状态</td><td>${currentBuild.result ?: 'SUCCESS'}</td></tr>
                                </table>
                                
                                <p>详细测试报告请查看附件中的 Markdown 文件。</p>
                                <p>Jenkins 构建地址: <a href="${env.BUILD_URL}">${env.BUILD_URL}</a></p>
                            </div>
                            <div class="footer">
                                <p>此邮件由 Jenkins 自动发送</p>
                            </div>
                        </body>
                        </html>
                    """
                    
                    def attachments = ''
                    if (fileExists("reports/${BUILD_NUMBER}/*.md")) {
                        attachments = "reports/${BUILD_NUMBER}/*.md"
                    }
                    
                    emailext(
                        subject: "[测试报告] ${params.CHIP} - ${params.MODEL} - 构建 #${BUILD_NUMBER}",
                        body: emailBody,
                        to: "${params.RECIPIENTS}",
                        attachmentsPattern: attachments,
                        mimeType: 'text/html'
                    )
                }
            }
        }

        stage('清理旧构建') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'EOF'
                            cd ${params.WORK_DIR}/builds 2>/dev/null || exit 0
                            ls -t | tail -n +21 | xargs -r rm -rf
                        EOF
                    """
                }
            }
        }
    }

    post {
        always {
            script {
                archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true, fingerprint: true

                try {
                    allure includeProperties: false,
                           jdk: '',
                           results: [[path: "reports/${BUILD_NUMBER}/allure-results"]]
                } catch (Exception e) {
                    echo "Allure 插件未安装"
                }

                echo """
                ========================================
                测试完成!
                ========================================
                构建: #${BUILD_NUMBER}
                芯片: ${params.CHIP}
                模型: ${params.MODEL}
                标记: ${params.MARKER}
                ----------------------------------------
                报告位置:
                  - 汇总报告: reports/${BUILD_NUMBER}/*.md
                  - Allure HTML: reports/${BUILD_NUMBER}/allure-html/
                ========================================
                """
            }
        }

        cleanup {
            cleanWs()
        }
    }
}

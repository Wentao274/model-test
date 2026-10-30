# AGENTS.md

## 新增 test_k 用例的强制同步规则（用户指定）

在 `tests/test_k_customer_issue.py` 下新增用例（K 类客户问题复现）时，
**必须同步以下全部位置**，缺一不可：

1. **用例本体**（`tests/test_k_customer_issue.py`）：
   - 测试方法（追加于文件末尾，不改动已有用例）；
   - 模块 docstring：新增用例条目 + 头部优先级范围枚举（当前口径：
     `K1-K7、K10-K26 为 P0，K8/K9 为 P1`）。
2. **注册**（`base/test_definitions.py`）：追加条目
   （id/标题/描述/方法名后缀/优先级）。
3. **Jenkinsfile**：用例选择参数（choice）列表追加测试节点
   （`tests/test_k_customer_issue.py::TestCustomerIssue::<方法名>`，
   注意前一项补逗号）。
4. **pytest.ini**：marker 描述中的用例编号枚举同步
   （如 `GLM53: …（K1/K2/K4/K14-K18, K20, K22-K26）`）。
5. **conftest.py**：采样参数豁免口径——豁免则加入
   `RAW_SAMPLING_PARAM_TESTS`；不豁免则在名单处补记注释
   （格式参照 K18/K20/K26 注释）。
6. **docs/test_k_customer_issue.md**：概览表新增行 + 详述章节
   （背景/请求构造/断言/判定矩阵/设计决策记录/注意事项）。
7. **checkpoints.md**：新增用例行 + P0 统计行数量与总计同步
   （如 `K1-K7, K10-K26 客户问题复现 24 项`、总计行）。
8. **README.md**（K 类行：测试点计数 + 用例枚举追加 + 总计行
   计数/P0 数）与 **docs/README.md**（K 类行测试点计数）——
   README 系列文档全部在维护范围（用户明确指定），计数与枚举
   不得停滞。

**验证**：改动后执行 `py_compile`（所有改动过的 .py），并做导入级
验证（方法存在、marks 齐全、test_definitions 注册正确）。

## mock 测试临时产物强制清理规则（用户指定）

使用 mock 服务/脚本做本地验证后，**必须清理全部临时文件和目录**，
包括：

1. 临时目录（`C:\Users\admin\AppData\Local\Temp\opencode`）下的
   mock 服务脚本、报文 dump、文档解压/提取产物（如 docx/PDF 的
   中间文件）、OCR 脚本与图片等一切验证辅助产物；
2. 工程目录（如 `tests/`）下测试运行期产生的临时文件
   （如 `k18_temp_skill_weekly.json`）——用例本身应 finally 兜底
   删除，验证后仍需人工确认无残留；
3. 验证完成后确认工作区无 mock 相关残留（不入库、不遗留）；
4. 本地 pytest 验证（含 `--collect-only`、连通性检查失败中止等
   未真正执行用例的运行）产生的运行骨架/报告目录同样属于残留
   ——清理范围必须覆盖全部运行输出根目录：`logs/`、
   `test_reports/`、`allure-results/`、**`allure-report/`**
   （注意与 allure-results 是两个不同目录，曾漏清被指出），按
   运行前后快照差集删除新增链，空根目录一并移除。

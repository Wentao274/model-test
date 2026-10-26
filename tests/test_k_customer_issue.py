"""
K. 客户问题复现测试

本测试类专门收录来自客户反馈的真实问题，将客户提供的 curl 命令还原为
标准模型请求进行复现与回归验证。优先级按客户工单标定：K1-K7 为 P0
（任何失败应阻断发布），K8/K9 为 P1。

环境注入约定：客户 curl 中的 URL、API key、模型名仅用于当时的问题定位，
不写入测试代码。与其他测试类一致，目标服务地址与凭证由 Jenkinsfile 构建
参数（BASE_URL / API_KEY / MODEL）透传至 pytest 的 --base-url / --api-key /
--model-name，经 conftest 的 api_client fixture 注入；curl 中的其余请求字段
（messages、tools、采样参数、user 等）按原样保留。

用例自包含约定：每个用例的常量（提示词、tools、参数等）与内部辅助函数
均定义在用例方法内部，不集中放在模块顶部——单个用例的全部信息可在
一处读完，用例之间互不干扰。

测试点：
- K1: Pydantic $defs/$ref Schema 工具调用（流式+思考+强制tool_choice） [P0]
  客户问题：glm-5.3 通过 /v1/chat/completions 发起流式请求报错【$$不兼容】。
  请求特征：thinking.type=enabled + stream + stream_options.include_usage +
  tool_choice 强制指定 function + tools 使用 Pydantic v2 生成的 JSON Schema
  （含 $defs/$ref 引用）。本用例按客户原始 curl 原样复现请求，验证服务端
  可正常接受该 Schema 并返回合法的强制工具调用结果。
- K2: 同一请求循环执行5次返回信息异常 [P0]
  客户问题：同一 curl 命令循环执行 5 次左右出现返回信息异常。
  请求特征：logprobs+top_logprobs+n+thinking+stream+stream_options+
  frequency_penalty/presence_penalty+user 字段 + X-Cache-Buster 防缓存请求头。
  本用例按客户原始 curl 原样复现并连续执行 5 次（相邻间隔 3s），断言每次的响应与内容均正常。
- K3: Anthropic 协议 prompt cache 未创建 [P0]
  客户问题：通过 Anthropic 协议（/anthropic/v1/messages，stream=true）发送带
  prompt cache 的请求，服务端日志 anthropic cache stats 中 cache_creation_tokens
  一直为 0（同时 cache_read_tokens 有值），说明 cache_control 断点未被落实、
  未创建缓存。本用例构造带 cache_control 断点的唯一长前缀，连续发送两次
  请求，断言第 1 次创建缓存（creation > 0）、第 2 次命中缓存（read > 0）。
- K4: frequency_penalty=-2 且不传 max_tokens 请求一直无返回 [P0]
  客户问题：fp=-2（OpenAI 规范 [-2,2] 的合法极值）且不传 max_tokens 时
  请求一直没有返回——fp<0 按出现次数奖励已出现 token，形成无饱和正反馈，
  循环 token 的 logit 压制 EOS 导致自然终止失效，输出只能跑到上下文
  上限，远超网关/客户端超时。平台修复契约：fp<0 按 0 处理（防御性
  钳制）。本用例输入保持 -2、不传 max_tokens，连发 3 次（消息各异、
  相邻间隔 3s——仅一次调用可能无法严谨验证），断言每次都按 fp=0 预期：
  预算时间内返回 + finish_reason 自然结束 + 内容非空，任一次失败报告
  第几次（不进 smoke 集）。
- K5: thinking.type=disabled 后思考未关闭 [P0]
  客户问题：thinking.type=disabled 后 reasoning_tokens 仍=100/75、
  reasoning_content 照常输出（官方端点实测应 rt 为空、无思考内容、正文
  正常返回；官方 FAQ 与实测不符，以实测为准），关思考相关功能（低延迟
  模式、关思考温度档）全部失效。本用例输入保持客户原值 disabled、显式
  temperature=0.6（官方关思考档唯一合法温度，契约见 K6）、不传
  max_tokens，连发 3 次（消息各异、相邻间隔 3s），断言每次均按官方实测
  预期：无思考内容（reasoning_content/reasoning）+ reasoning_tokens
  为空（0/缺失，兼容两种字段拼写）+ 正文正常返回且自然结束，任一次
  失败报告第几次。
- K6: 关思考温度档未联动校验 [P0]
  官方契约（kimi-k3 官方说明）：thinking 模式与 temperature 档位联动
  ——disabled 下仅允许 0.6（给 1 或 0 会 400 并报 "only 0.6 is allowed
  for this model in non-thinking mode"）、enabled 下仅允许 1（给 0.6
  或 0 会 400 并报 "only 1 is allowed for this model in thinking
  mode"）。客户影响：关思考相关功能（关思考温度档）失效。本用例对
  6 个组合各发一次请求（参数校验为确定性行为，无需多次连发），断言
  合法组合 200+正文非空、非法组合 400+错误信息含官方文案（忽略大小写
  子串匹配）。
- K7: 思考强度档位思考长度倒挂（官方 reasoning_effort） [P0]
  官方契约（kimi-k3 官方文档 use-reasoning-effort/kimi-k3-quickstart）：
  思考强度为顶层 reasoning_effort 参数（K2.x 的 thinking 配置在 K3
  已废弃，官方迁移指引为移除 thinking 改用 reasoning_effort），K3
  恒开思考；官方预期思考长度（reasoning_tokens）随档位递增。本用例
  只按官方格式传参（顶层 reasoning_effort，无回退），请求顺序（客户
  指定）：low → high → max 后比对思考长度，再按 max → high → low
  逆向重发并再次比对（正逆两轮排除请求顺序相关干扰，均按 low <
  high < max 三档软对比，medium 不参与对比）；最后依次验证 medium
  顶层（按官方 200 放行）与 medium 嵌套（thinking.effort=medium
  预期 400——废弃的 K2.x thinking 配置下 medium 为非法档位，客户
  指定契约）。请求内容与温度完全相同（temperature=1，开思考档契约
  温度，见 K6），相邻间隔 3s。硬断言：每次官方档请求（升序轮+降序轮+
  medium 顶层）200+正文非空+自然结束；嵌套 thinking.effort=medium
  400。档位倒挂/持平不判失败，仅告警记入报告（行为质量偏离而非
  服务故障）（不进 smoke 集：max 档思考生成为长耗时请求，同 K4
  理由）。
- K8: required+闲聊必须调用工具（客户工单级别） [P1]
  客户工单原始问题：tool_choice=required + 闲聊 "Reply with
  exactly: OK"（无工具意图）下不发起工具调用——tool_calls 键缺
  失、finish=length、completion_tokens 恒被吃满 max_tokens（关
  思考 1000/3000 级别均如此）、正文仅 "OK"、耗时 ~15.6s（正常
  ~1.5s，双峰）；开思考下 reasoning 消耗远小于预算但整体仍被
  吃满（mt=3000 仍不调）。预期（工单）：required 必须发起工具
  调用——finish 应为 tool_calls 而非 length、关思考 ct 应较
  小、开思考 rt 应 < max_tokens、正文应正常收到调用工具的响应
  信息。轮次（客户实测级别）：关思考 mt=1000、关思考 mt=3000、
  开思考 mt=3000（get_weather 工具）。硬断言：每轮 200+choices+
  usage 存在；tool_calls 存在且为 get_weather 调用（arguments
  合法 JSON，city 值不限定）；finish_reason=="tool_calls"（而非
  length，关/开思考均不允许）；ct < max_tokens（关思考下应较
  小）；开思考 rt < max_tokens（rt 双拼写兼容）。temperature 按
  网关档位联动取 0.6/1（非该值被 400 拒绝）。耗时双峰仅日志留
  痕。（不进 smoke 集：缺陷轮 15.6s 级长耗时+缺陷概率性）
- K9: required+闲聊必须强制调用工具（按官方行为） [P1]
  官方 api.moonshot.cn/kimi-k3 实测：闲聊 "Reply with exactly:
  OK" + required → finish=tool_calls、强制返回 get_weather 调用
  （city 瞎猜 London/UNKNOWN，值不限定）、reasoning 仅 38 token
  ——符合 [OI] required「必须发起至少一次工具调用」规范；Alaya
  同场景缺陷：finish=length、reasoning 吃满 256/2000 预算、
  tool_calls=None；有工具意图时（北京天气）两站一致正常。
  本用例按官方行为为预期（与 K8 同场景不同级别：K8 为客户工单
  级别，本用例镜像 Alaya 缺陷实测级别）：关/开思考 × mt=256/
  2000。硬断言：每轮 200+choices+usage 存在；tool_calls 强制
  返回（get_weather、arguments 合法 JSON，city 值不限定）；
  finish_reason=="tool_calls"；ct < max_tokens；开思考 rt <
  max_tokens（rt 双拼写兼容）。temperature 按网关档位联动取
  0.6/1。耗时双峰仅日志留痕。（不进 smoke 集：缺陷轮 15.6s
  级长耗时+缺陷概率性）
"""

import json
import time
import uuid
import pytest
import requests
from typing import Any, Dict, List

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestCustomerIssue(BaseTest, StreamingTestMixin):
    """客户问题复现测试类

    每个用例自包含：该用例的常量与内部辅助函数均定义在用例方法内部
    （见模块 docstring 的"用例自包含约定"）。
    """

    def get_test_category(self) -> str:
        return "K. 客户问题复现"

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_pydantic_schema_tool_call_stream(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K1 [P0]: 客户问题 - Pydantic $defs/$ref Schema 工具调用报【$$不兼容】

        客户使用 glm-5.3 发起 thinking+stream+强制 tool_choice 的通话分析请求，
        tools 的 parameters 为 Pydantic v2 自动生成的 JSON Schema（含
        $defs/$ref 引用），服务端报错【$$不兼容】。本用例按客户原始 curl
        原样复现请求，验证：
        - 服务端正常处理该请求并返回流式 chunks（不报 $$ 相关错误）
        - 返回强制指定的 submit_d2_product 工具调用（含 id）
        - 工具参数为合法 JSON 且满足 schema 必填项（core_work_type）
        - stream_options.include_usage 的 usage 返回（缺失仅告警）
        """
        # K1: 客户原始请求的 system 提示词（与 curl 完全一致）
        K1_SYSTEM_PROMPT = (
            "你是通话内容分析师。请根据通话内容完成指定维度的结构化提取。只提取客观事实。"
        )

        # K1: 客户原始请求的 user 消息（与 curl 完全一致）
        K1_USER_PROMPT = (
            "请从以下通话中提取产品与工作分类信息。\n"
            "核心工作类型：产品售卖|大搜解搁|充值续费|账户优化|流程处理|客情维护|"
            "活动通知|操作指引\n"
            "\n"
            "## 通话内容\n"
            "\n"
            "坐席：'喂你好百度，'\n"
            "客户：'您说，'\n"
            "坐席：'嗯是这样的我们那个vip神经元这个账户的话是已经分到我这边了，"
            "然后跟您说一下，后续的账户负责是通过我这边给您去做维护，'"
            "'然后后续的话我让这个咱们的开户销售拉个群到时候我们有什么问题"
            "直接在群里沟通好吧，'\n"
            "客户：'嗯可以啊，''就是我没用过咱们这平台有培训吗？'\n"
            "坐席：'培训的话我这边可以教您一些比较基础的，然后详细的话它百度这边"
            "好像是没有可以外发的，到时候我看一下有什么渠道让您去学习一下看一下，'\n"
            "客户：'嗯，'\n"
            "坐席：'嗯好的好的，拜拜拜，'\n"
            "客户：'四分，'"
        )

        # K1: 客户原始请求的 tools 定义 —— Pydantic v2 自动生成的 JSON
        # Schema，parameters 中含 $defs 定义与 $ref 引用（【$$不兼容】问题
        # 的核心对象）
        K1_TOOLS_SUBMIT_D2_PRODUCT = [
            {
                "type": "function",
                "function": {
                    "name": "submit_d2_product",
                    "description": "提交产品与工作分类分析结果",
                    "parameters": {
                        "$defs": {
                            "ProductDetail": {
                                "additionalProperties": True,
                                "properties": {
                                    "customer_response": {
                                        "default": "",
                                        "title": "Customer Response",
                                        "type": "string",
                                    },
                                    "depth": {
                                        "default": "",
                                        "title": "Depth",
                                        "type": "string",
                                    },
                                    "evidence": {
                                        "default": "",
                                        "title": "Evidence",
                                        "type": "string",
                                    },
                                    "mention_type": {
                                        "default": "",
                                        "title": "Mention Type",
                                        "type": "string",
                                    },
                                    "outcome": {
                                        "default": "",
                                        "title": "Outcome",
                                        "type": "string",
                                    },
                                    "product": {
                                        "default": "",
                                        "title": "Product",
                                        "type": "string",
                                    },
                                },
                                "title": "ProductDetail",
                                "type": "object",
                            },
                            "SaleSignals": {
                                "additionalProperties": True,
                                "properties": {
                                    "has_signal": {
                                        "default": False,
                                        "title": "Has Signal",
                                        "type": "boolean",
                                    },
                                    "signal_strength": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}],
                                        "default": None,
                                        "title": "Signal Strength",
                                    },
                                    "signal_type": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}],
                                        "default": None,
                                        "title": "Signal Type",
                                    },
                                },
                                "title": "SaleSignals",
                                "type": "object",
                            },
                        },
                        "properties": {
                            "biz_scenario": {
                                "default": "",
                                "title": "Biz Scenario",
                                "type": "string",
                            },
                            "core_work_type": {
                                "title": "Core Work Type",
                                "type": "string",
                            },
                            "product_details": {
                                "items": {"$ref": "#/$defs/ProductDetail"},
                                "title": "Product Details",
                                "type": "array",
                            },
                            "product_tags": {
                                "items": {"type": "string"},
                                "title": "Product Tags",
                                "type": "array",
                            },
                            "sale_signals": {"$ref": "#/$defs/SaleSignals"},
                        },
                        "required": ["core_work_type"],
                        "title": "ProductSchema",
                        "type": "object",
                    },
                },
            }
        ]

        # K1: 客户原始请求的 tool_choice —— 强制调用 submit_d2_product
        K1_TOOL_CHOICE = {"type": "function", "function": {"name": "submit_d2_product"}}

        def collect_stream_tool_calls(
            result: Dict[str, Any],
        ) -> List[Dict[str, Any]]:
            """从流式 chunks 中聚合 tool_calls 增量片段

            OpenAI 流式协议中 tool_calls 以增量片段下发（按 index 分片，
            function.arguments 逐段追加），需按 index 聚合才是完整调用。
            """
            aggregated: Dict[int, Dict[str, Any]] = {}
            for chunk in result.get("chunks", []):
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    entry = aggregated.setdefault(
                        idx, {"id": None, "name": "", "arguments": ""}
                    )
                    if tc.get("id"):
                        entry["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        entry["name"] += fn["name"]
                    if fn.get("arguments"):
                        entry["arguments"] += fn["arguments"]
            return [aggregated[k] for k in sorted(aggregated)]

        test_logger.info(
            "=== 测试开始: 客户问题 - Pydantic $defs/$ref Schema 工具调用 ==="
        )

        messages = [
            {"role": "system", "content": K1_SYSTEM_PROMPT},
            {"role": "user", "content": K1_USER_PROMPT},
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "max_tokens": 4096,
                "temperature": 0.1,
                "thinking": {"type": "enabled"},
                "tools": "submit_d2_product ($defs/$ref schema)",
                "tool_choice": "forced submit_d2_product",
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        )

        # 按客户原始 curl 原样下发：thinking + stream + 强制 tool_choice +
        # Pydantic $defs/$ref Schema + stream_options.include_usage
        response_iter = api_client.chat_completion_stream(
            messages,
            temperature=0.1,
            max_tokens=4096,
            thinking={"type": "enabled"},
            tools=K1_TOOLS_SUBMIT_D2_PRODUCT,
            tool_choice=K1_TOOL_CHOICE,
            stream_options={"include_usage": True},
        )
        result = self.collect_stream_chunks(response_iter)
        tool_calls = collect_stream_tool_calls(result)

        self.log_full_response(
            test_logger,
            {
                "chunks_count": len(result["chunks"]),
                "content": result["content"][:2000],
                "reasoning": (
                    result["reasoning"][:2000] if result["reasoning"] else ""
                ),
                "tool_calls": tool_calls,
            },
            "K1-客户问题复现($defs/$ref Schema)",
        )

        # 核心验证：含 $defs/$ref Schema 的请求可被正常处理
        assert len(result["chunks"]) > 0, (
            "No streaming chunks received — 客户问题复现失败：服务端未能处理"
            "含 $defs/$ref Schema 的工具调用请求（原始报错【$$不兼容】）"
        )

        # 工具调用场景 finish_reason 应为 tool_calls；
        # 思考模型在 reasoning 耗尽 max_tokens 时可能为 length
        finish_reason = None
        for chunk in reversed(result["chunks"]):
            if chunk.get("choices"):
                finish_reason = chunk["choices"][0].get("finish_reason")
                break
        assert finish_reason in ("tool_calls", "stop", "eos", "ended", "length"), (
            f"finish_reason should be 'tool_calls' (or stop/eos/ended/length), "
            f"got '{finish_reason}'"
        )
        test_logger.info(f"finish_reason: {finish_reason}")

        # 强制 tool_choice 下必须返回指定的工具调用
        assert len(tool_calls) > 0, (
            "tool_choice 强制指定 submit_d2_product，"
            "但流式响应中未聚合到任何 tool_calls"
        )
        first_call = tool_calls[0]
        assert first_call["name"] == "submit_d2_product", (
            f"Expected forced tool 'submit_d2_product', got '{first_call['name']}'"
        )
        assert first_call.get("id"), "Tool call should have non-empty 'id'"

        # 工具参数必须是合法 JSON（流式增量聚合后）
        args_raw = first_call["arguments"]
        try:
            args = json.loads(args_raw) if args_raw.strip() else {}
        except json.JSONDecodeError as e:
            pytest.fail(
                f"Tool call arguments is not valid JSON: {args_raw[:500]}, error: {e}"
            )

        # schema 必填项校验：required = ["core_work_type"]
        assert "core_work_type" in args, (
            f"Tool arguments missing required field 'core_work_type': {args}"
        )
        core_work_type = args["core_work_type"]
        assert (
            isinstance(core_work_type, str) and core_work_type.strip()
        ), f"'core_work_type' should be a non-empty string, got: {core_work_type!r}"

        # stream_options.include_usage 软校验：usage 缺失仅告警（部分部署不实现）
        usage = next(
            (c.get("usage") for c in reversed(result["chunks"]) if c.get("usage")),
            None,
        )
        if not usage:
            test_logger.warning(
                "stream_options.include_usage=true 但流式响应中未携带 usage，"
                "当前部署可能未实现该参数"
            )

        test_logger.info(
            f"客户问题复现通过: tool={first_call['name']}, "
            f"core_work_type={core_work_type}, "
            f"reasoning_len={len(result['reasoning'])}, "
            f"chunks={len(result['chunks'])}"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_repeated_request_stability(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K2 [P0]: 客户问题 - 同一请求循环执行5次返回信息异常

        客户循环执行同一 curl 命令（thinking+stream+logprobs+top_logprobs+n+
        frequency_penalty/presence_penalty+user 字段+X-Cache-Buster 防缓存头）
        5 次左右出现返回信息异常。本用例按客户原始 curl 原样复现并连续执行
        5 次（相邻请求间隔 3s），验证：
        - 每次请求均被服务端正常处理并返回流式 chunks
        - 每次 finish_reason 合法
        - 每次正式回答内容非空
        5 次全部正常才判定通过；任一次异常即失败，并报告第几次及异常详情。
        """
        # K2: 客户原始请求的 system 提示词（与 curl 完全一致）
        K2_SYSTEM_PROMPT = "无论什么问题，你每次回答都必须以“很高兴为您服务”开头"

        # K2: 客户原始请求的 user 消息（与 curl 完全一致）
        K2_USER_PROMPT = "介绍一下，RPG游戏，40字🤔"

        # K2: 客户原始请求的 user 字段——终端用户标识（与 curl 完全一致）
        K2_USER_ID = "a74685ef7268c396f0b842750bd7ab3252b37e7e3619ab33126946ee63d867e0"

        # K2: 循环执行次数（客户反馈"请求5次左右返回信息异常"）
        K2_REPEAT_TIMES = 5

        # K2: 相邻两次请求的间隔（秒）——第 1~4 次完成后间隔 3s 再发起下一次
        # （末次后不等待），模拟客户循环执行 curl 的节奏
        K2_REQUEST_INTERVAL_SECONDS = 3

        test_logger.info(
            "=== 测试开始: 客户问题 - 同一请求循环执行 %d 次返回信息异常 ==="
            % K2_REPEAT_TIMES
        )

        messages = [
            {"role": "system", "content": K2_SYSTEM_PROMPT},
            {"role": "user", "content": K2_USER_PROMPT},
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "max_tokens": 2048,
                "temperature": 1,
                "thinking": {"type": "enabled"},
                "logprobs": True,
                "top_logprobs": 4,
                "n": 1,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "top_p": 0.95,
                "user": K2_USER_ID,
                "stream": True,
                "stream_options": {"include_usage": True},
                "X-Cache-Buster": "每次迭代更新（$(date +%s)）",
            },
        )

        for i in range(1, K2_REPEAT_TIMES + 1):
            # 客户 curl 通过 -H "X-Cache-Buster: $(date +%s)" 防缓存，
            # 每次执行生成新值；此处同样在每次迭代前更新该请求头
            # （追加迭代序号保证 5 次快速执行间取值也唯一）
            api_client.session.headers["X-Cache-Buster"] = (
                f"{int(time.time())}_{i}"
            )

            # 按客户原始 curl 原样下发全部参数
            try:
                response_iter = api_client.chat_completion_stream(
                    messages,
                    temperature=1,
                    max_tokens=2048,
                    logprobs=True,
                    n=1,
                    thinking={"type": "enabled"},
                    user=K2_USER_ID,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream_options={"include_usage": True},
                    top_logprobs=4,
                    top_p=0.95,
                )
                result = self.collect_stream_chunks(response_iter)
            except Exception as e:
                pytest.fail(
                    f"第 {i}/{K2_REPEAT_TIMES} 次请求异常"
                    f"——客户问题复现失败：{e}"
                )

            # 响应正常：流式 chunks 非空（HTTP 非 200 时 chat_completion_stream
            # 已直接抛异常，走到这里说明请求本身成功）
            assert len(result["chunks"]) > 0, (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求未返回任何 SSE chunk"
                "——客户问题复现失败：循环执行出现返回信息异常"
            )

            # 响应正常：finish_reason 合法
            finish_reason = None
            for chunk in reversed(result["chunks"]):
                if chunk.get("choices"):
                    finish_reason = chunk["choices"][0].get("finish_reason")
                    break
            assert finish_reason in ("tool_calls", "stop", "eos", "ended", "length"), (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求 finish_reason 异常: "
                f"'{finish_reason}'"
            )

            # 内容正常：正式回答非空
            content = result["content"].strip()
            assert content, (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求返回内容为空"
                "——客户问题复现失败：循环执行出现返回信息异常"
            )

            # 软观察（不判失败）：system prompt 要求每次回答以
            # "很高兴为您服务"开头，偏离时记录告警供问题定位
            if not content.startswith("很高兴为您服务"):
                test_logger.warning(
                    f"第 {i}/{K2_REPEAT_TIMES} 次回答未以'很高兴为您服务'开头"
                    f"（system prompt 要求）: {content[:80]}"
                )

            # 软观察：stream_options.include_usage 的 usage 返回
            usage = next(
                (c.get("usage") for c in reversed(result["chunks"]) if c.get("usage")),
                None,
            )
            if not usage:
                test_logger.warning(
                    f"第 {i}/{K2_REPEAT_TIMES} 次请求 stream_options.include_usage=true "
                    "但流式响应中未携带 usage"
                )

            test_logger.info(
                f"第 {i}/{K2_REPEAT_TIMES} 次正常: finish_reason={finish_reason}, "
                f"content={content[:60]}, "
                f"reasoning_len={len(result['reasoning'])}, "
                f"chunks={len(result['chunks'])}, usage={'有' if usage else '无'}"
            )

            # 相邻请求间隔（末次后不等待）
            if i < K2_REPEAT_TIMES:
                time.sleep(K2_REQUEST_INTERVAL_SECONDS)

        test_logger.info(
            f"客户问题复现通过: 同一请求连续执行 {K2_REPEAT_TIMES} 次，"
            "响应与内容均正常"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_anthropic_prompt_cache_creation(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K3 [P0]: 客户问题 - Anthropic 协议请求 cache_creation_tokens 一直为 0

        客户通过 Anthropic 协议（/anthropic/v1/messages，stream=true）发送带
        prompt cache 的请求，服务端日志 anthropic cache stats 中
        cache_creation_tokens 一直为 0（同时 cache_read_tokens 有值），
        说明 cache_control 断点未被落实。本用例构造带 cache_control 断点的
        唯一长前缀（约 11 万 tokens，对齐客户 prompt_tokens=111283 的场景
        规模，同时远超 Anthropic 协议最小可缓存长度），连续发送两次请求：
        - 第 1 次（唯一新前缀）：cache_creation_input_tokens > 0（创建缓存）
        - 第 2 次（相同前缀）：cache_read_input_tokens > 0（命中缓存）
        字段名兼容 Anthropic 协议（cache_creation_input_tokens）与客户日志
        网关内部名（cache_creation_tokens）两种拼写。
        """
        # K3: Anthropic 协议版本头。2023-06-01 为长期 GA 版本（2023.6 起两年
        # 多内唯一主流版本，第三方兼容网关的事实标准）；官方 SDK v2.1.0+ 已
        # 升到 2026-10-21，但被测对象为客户的 Anthropic 兼容网关（非官方
        # API），新版本日期更可能被网关版本校验拒绝，故沿用兼容面最广的
        # 2023-06-01。Anthropic 版本头用于钉住协议行为，老版本不会过期失效；
        # K3 依赖的 prompt caching（cache_control）在 2023-06-01 上即为 GA。
        # 若目标网关升级要求新版本，改此常量即可。
        K3_ANTHROPIC_VERSION = "2023-06-01"

        # K3: 输出 token 上限——缓存断言只关心 input 侧 usage，输出无需过长
        K3_MAX_TOKENS = 512

        # K3: 可缓存前缀的填充文本。客户问题的 prompt_tokens=111283（超长
        # 上下文触发 prompt cache），按中文 ~1.3-1.7 字符/token 保守折算，
        # 需约 19 万字符才能保证达到 11 万 tokens 量级（同时远超 Anthropic
        # 协议最小可缓存长度 1024 tokens）。规模对齐客户场景的原因：若缺陷
        # 为规模相关（仅超长前缀的 cache_control 不落实），过短的测试前缀
        # 将无法复现。
        K3_PREFIX_FILLER_UNIT = (
            "本知识库涵盖产品规格、接口说明、计费策略、常见问题与处理流程，"
            "供客服助手检索引用。"
        )
        K3_PREFIX_TARGET_CHARS = 190000
        K3_PREFIX_FILLER = K3_PREFIX_FILLER_UNIT * (
            K3_PREFIX_TARGET_CHARS // len(K3_PREFIX_FILLER_UNIT) + 1
        )

        # K3: 超长前缀（~11 万 tokens）的 prefill 耗时显著，参考 D 类用例的
        # 超时保护模式，保证单次请求超时下限
        K3_MIN_REQUEST_TIMEOUT = 1200

        # K3: 用户消息（缓存断言不依赖回答内容）
        K3_USER_MESSAGE = "请回复：收到。"

        def anthropic_stream_request(
            payload: Dict[str, Any], label: str
        ) -> Dict[str, Any]:
            """通过 Anthropic 协议发送流式请求并解析 SSE，返回合并后的 usage

            端点为 {base_url}/anthropic/v1/messages（与客户网关布局一致），
            鉴权使用 x-api-key 头 + anthropic-version 协议头。
            usage 提取自 message_start（message.usage）与 message_delta
            （usage），后者覆盖前者（累计值）。
            """
            url = f"{api_client.base_url}/anthropic/v1/messages"
            headers = {"anthropic-version": K3_ANTHROPIC_VERSION}
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            try:
                response = api_client.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=api_client.timeout,
                    stream=True,
                )
            except Exception as e:
                pytest.fail(f"{label} 发送失败（{url}）: {e}")

            if response.status_code != 200:
                pytest.fail(
                    f"{label} 请求失败 HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            usage: Dict[str, Any] = {}
            events = 0
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                events += 1
                evt_usage = None
                if event.get("type") == "message_start":
                    evt_usage = (event.get("message") or {}).get("usage")
                elif event.get("type") == "message_delta":
                    evt_usage = event.get("usage")
                if evt_usage:
                    usage.update(evt_usage)
            if events == 0:
                pytest.fail(f"{label} 未返回任何 SSE 事件（{url}）")
            test_logger.info(f"{label} usage: {usage}")
            return usage

        def cache_usage_field(usage: Dict[str, Any], *names: str) -> int:
            """从 usage 中取缓存计数值，兼容协议字段名与网关内部字段名两种拼写"""
            for name in names:
                value = usage.get(name)
                if isinstance(value, (int, float)) and value > 0:
                    return int(value)
            return 0

        test_logger.info(
            "=== 测试开始: 客户问题 - Anthropic 协议 prompt cache 未创建 ==="
        )

        # 唯一批次号置于前缀最前：保证本次运行不会命中历史运行遗留的缓存
        run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        prefix_text = f"文档批次编号：{run_id}\n" + K3_PREFIX_FILLER

        # 超长前缀（~11 万 tokens）prefill 耗时显著，参考 D 类用例的
        # 超时保护模式：保证单次请求超时下限（配置已 >= 该值时为 no-op）
        original_timeout = api_client.timeout
        api_client.timeout = max(original_timeout, K3_MIN_REQUEST_TIMEOUT)
        try:
            payload = {
                "model": api_client.model_name,
                "max_tokens": K3_MAX_TOKENS,
                "system": [
                    {
                        "type": "text",
                        "text": prefix_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": K3_USER_MESSAGE}],
                "stream": True,
            }

            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "system",
                        "content": (
                            f"[可缓存长前缀 {len(prefix_text)} 字符，批次 {run_id}]"
                        ),
                    },
                    {"role": "user", "content": K3_USER_MESSAGE},
                ],
                {
                    "protocol": "anthropic (/anthropic/v1/messages)",
                    "anthropic-version": K3_ANTHROPIC_VERSION,
                    "max_tokens": K3_MAX_TOKENS,
                    "stream": True,
                    "cache_control": "ephemeral（system 前缀断点）",
                },
            )

            # 第 1 次请求：唯一新前缀，期望触发缓存创建
            usage1 = anthropic_stream_request(payload, "第 1 次请求（唯一前缀）")
            creation1 = cache_usage_field(
                usage1, "cache_creation_input_tokens", "cache_creation_tokens"
            )
            read1 = cache_usage_field(
                usage1, "cache_read_input_tokens", "cache_read_tokens"
            )
            input1 = usage1.get("input_tokens", 0)
            test_logger.info(
                f"第 1 次请求（唯一前缀）: input_tokens={input1}, "
                f"cache_creation={creation1}, cache_read={read1}"
            )
            if input1 and input1 < 1024:
                test_logger.warning(
                    f"input_tokens={input1} 低于 Anthropic 协议最小可缓存长度"
                    "（1024 tokens），cache_creation 为 0 可能是前缀过短所致，"
                    "请加大 K3_PREFIX_TARGET_CHARS"
                )
            elif input1 and input1 < 100000:
                test_logger.info(
                    f"input_tokens={input1} 低于客户场景规模（111283），"
                    "如疑似规模相关问题请加大 K3_PREFIX_TARGET_CHARS"
                )

            # 第 2 次请求：相同前缀，期望命中缓存
            usage2 = anthropic_stream_request(payload, "第 2 次请求（相同前缀）")
            creation2 = cache_usage_field(
                usage2, "cache_creation_input_tokens", "cache_creation_tokens"
            )
            read2 = cache_usage_field(
                usage2, "cache_read_input_tokens", "cache_read_tokens"
            )
            test_logger.info(
                f"第 2 次请求（相同前缀）: cache_creation={creation2}, "
                f"cache_read={read2}"
            )

            # 核心断言 1：携带 cache_control 断点的新前缀必须创建缓存
            # （客户问题：cache_creation_tokens 一直为 0，未创建缓存）
            assert creation1 > 0, (
                f"客户问题复现失败：携带 cache_control 断点的新前缀请求 "
                f"cache_creation_tokens={creation1}（一直为 0，未创建缓存）。"
                f"input_tokens={input1}, usage={usage1}"
            )

            # 核心断言 2：相同前缀的第 2 次请求必须命中缓存
            assert read2 > 0, (
                f"相同前缀第 2 次请求未命中缓存: cache_read_tokens={read2}"
                f"（第 1 次已创建 {creation1}）, usage={usage2}"
            )

            test_logger.info(
                f"客户问题复现通过: 第 1 次创建 {creation1} tokens, "
                f"第 2 次命中 {read2} tokens"
            )
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    def test_negative_frequency_penalty_treated_as_zero(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K4 [P0]: 客户问题 - frequency_penalty=-2 且不传 max_tokens 请求一直无返回

        客户问题：frequency_penalty=-2（OpenAI 规范 [-2,2] 的合法极值）且
        不传 max_tokens 时请求一直没有返回。机理：fp<0 按出现次数奖励已
        出现 token，形成无饱和正反馈，循环 token 的 logit 持续增长压制
        EOS，自然终止失效；输出上限=剩余上下文（可能十余万 tokens），
        生成耗时远超网关/客户端超时，观感即"一直没有返回"。
        平台修复契约：frequency_penalty<0 时按 0 处理（防御性钳制）。
        因此本用例输入保持客户原值 -2、不传 max_tokens，连发 3 次
        （消息各异、相邻间隔 3s——仅一次调用可能无法严谨验证问题），
        断言每次都按 fp=0 的预期结果：
        - 单次响应时间预算内返回（超预算无响应 = 客户问题复现）
        - finish_reason 为自然结束（stop/eos/ended，而非跑满上限的 length）
        - 回答内容非空
        3 次全部正常结束才判定通过；任一次异常即失败，并报告第几次。
        本用例不进 smoke 集：未修复时最坏耗时约
        3×K4_RESPONSE_BUDGET_SECONDS，避免拖慢冒烟套件
        （决策记录见 docs/test_k_customer_issue.md）。
        """
        # K4: 客户原始请求的 frequency_penalty 取值——OpenAI 规范允许
        # [-2, 2]，-2 为合法极值。fp<0 按出现次数奖励已出现 token（正
        # 反馈），是"放大重复"的文档化数学行为；客户问题出在不传
        # max_tokens 时无界生成无法终止。
        K4_FREQUENCY_PENALTY = -2

        # K4: 3 个不同的用户提示词（客户原始 prompt 未提供）。连发 3 次、
        # 消息各异：单次调用可能无法严谨验证——钳制若未生效，单次请求
        # 也可能侥幸自然结束；不同消息降低偶然性，未钳制的退化重复更
        # 难在不同 prompt 下全部侥幸通过
        K4_USER_PROMPTS = (
            "请用一段话介绍大语言模型的工作原理。",
            "请简要说明云计算能给企业带来的核心价值。",
            "请列举两种常见的排序算法，并各用一句话说明其特点。",
        )

        # K4: 相邻两次请求的间隔（秒）——第 1、2 次完成后间隔 3s 再发起
        # 下一次（末次后不等待），3 次总计额外约 6s
        K4_REQUEST_INTERVAL_SECONDS = 3

        # K4: 单次请求的响应时间预算（秒），按请求独立生效（3 次共享同一
        # 预算客户端，timeout 在每次请求上生效）。平台修复契约为 fp<0 按
        # 0 处理，修复后每次请求与普通请求无异、数秒内即应返回；未修复
        # 时退化重复会一直生成到上下文上限，远超任何网关/客户端超时。
        # 预算即挂起检测护栏：超预算无响应 = 客户问题复现。取 120s：
        # 远大于正常请求耗时，又控制在单用例可承受范围（3 次最坏 360s）。
        K4_RESPONSE_BUDGET_SECONDS = 120

        # K4: 修复契约下的自然结束原因——未传 max_tokens，正常生成应自然
        # 停止；length 表示生成跑满输出上限（=剩余上下文），即退化重复
        # 未被钳制的特征
        K4_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - frequency_penalty=-2 不传 max_tokens 无返回"
            f"（连发 {len(K4_USER_PROMPTS)} 次，消息各异）==="
        )

        # 专用预算客户端（F8 先例）：短超时 + retry_times=0，保证未修复时
        # 单次最坏耗时 = 单次预算而非预算×(重试+1)；构造时只透传鉴权与
        # 模型，不携带全局采样参数，保持客户原始参数面
        budget_client = ModelAPIClient(
            api_key=api_client.api_key,
            base_url=api_client.base_url,
            model_name=api_client.model_name,
            timeout=K4_RESPONSE_BUDGET_SECONDS,
            config=api_client.config,
            retry_times=0,
        )
        url = f"{budget_client.base_url}/v1/chat/completions"

        def run_request(index: int, prompt: str) -> None:
            """K4 单次请求核心逻辑：fp=-2、不传 max_tokens，按 fp=0 预期断言

            任一步失败即判失败并报告第 {index}/{len(K4_USER_PROMPTS)} 次。
            """
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "frequency_penalty": K4_FREQUENCY_PENALTY,
                    "max_tokens": "未传（客户原始请求）",
                    "stream": False,
                    "request": f"第 {index}/{len(K4_USER_PROMPTS)} 次（消息各异）",
                },
            )

            # 客户请求形态：仅 model/messages/frequency_penalty，不带
            # max_tokens。chat_completion 封装会强制注入默认 max_tokens=2048
            # 与 temperature，破坏"不传 max_tokens"的前提，故按 K3 先例
            # 手工构造 payload 直发
            payload = {
                "model": budget_client.model_name,
                "messages": messages,
                "frequency_penalty": K4_FREQUENCY_PENALTY,
                "stream": False,
            }

            started = time.time()
            try:
                response = budget_client._post_with_retry(url, payload, stream=False)
            except requests.exceptions.Timeout as e:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求客户问题复现失败："
                    f"frequency_penalty={K4_FREQUENCY_PENALTY} 且未传 max_tokens，"
                    f"{K4_RESPONSE_BUDGET_SECONDS}s 内无任何响应（fp<0 未按 0 处理，"
                    f"退化重复导致无界生成），耗时 {time.time() - started:.1f}s: {e}"
                )
            except Exception as e:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求发送异常（{url}）: {e}"
                )
            elapsed = time.time() - started

            if response.status_code != 200:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求失败 "
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )

            choices = result.get("choices") or []
            assert choices, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            choice = choices[0]
            message = choice.get("message") or {}
            content = (message.get("content") or "").strip()
            finish_reason = choice.get("finish_reason")

            # 核心断言 1：修复契约（fp<0 按 0 处理）下应自然结束——未传
            # max_tokens，正常生成自然停止；length 表示生成跑满输出上限
            # （=剩余上下文），即退化重复未被钳制的特征
            assert finish_reason in K4_NATURAL_FINISH_REASONS, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次客户问题复现失败："
                f"frequency_penalty={K4_FREQUENCY_PENALTY} 应按 0 处理（防御性"
                f"钳制），但 finish_reason='{finish_reason}'（期望自然结束 "
                f"{K4_NATURAL_FINISH_REASONS}；length 表示生成跑满输出上限，"
                f"即退化重复未被钳制），耗时 {elapsed:.1f}s，消息: {prompt[:30]}"
            )

            # 核心断言 2：回答内容非空
            assert content, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次客户问题复现失败："
                f"返回内容为空，finish_reason={finish_reason}，"
                f"耗时 {elapsed:.1f}s，消息: {prompt[:30]}"
            )

            # 软观察：耗时超过单次预算一半时告警（修复后正常应数秒内返回）
            if elapsed > K4_RESPONSE_BUDGET_SECONDS / 2:
                test_logger.warning(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求耗时 {elapsed:.1f}s，"
                    f"超过预算 {K4_RESPONSE_BUDGET_SECONDS}s 的一半（修复后正常应"
                    f"数秒内返回），请关注服务负载"
                )

            TestLogger.log_response(
                test_logger, result, f"K4-响应（第 {index} 次）"
            )
            test_logger.info(
                f"第 {index}/{len(K4_USER_PROMPTS)} 次正常（fp="
                f"{K4_FREQUENCY_PENALTY} 按 0 处理）: finish_reason={finish_reason}, "
                f"completion_tokens="
                f"{(result.get('usage') or {}).get('completion_tokens')}, "
                f"耗时 {elapsed:.1f}s, 消息: {prompt[:30]}"
            )

        try:
            for i, prompt in enumerate(K4_USER_PROMPTS, start=1):
                run_request(i, prompt)
                # 相邻请求间隔（末次后不等待）
                if i < len(K4_USER_PROMPTS):
                    time.sleep(K4_REQUEST_INTERVAL_SECONDS)
        finally:
            budget_client.close()

        test_logger.info(
            "客户问题复现通过: frequency_penalty=-2 已按 0 处理，未传 "
            f"max_tokens 连发 {len(K4_USER_PROMPTS)} 次（消息各异）"
            "均正常返回并自然结束"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_thinking_disabled_suppresses_reasoning(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K5 [P0]: 客户问题 - thinking.type=disabled 后思考未关闭

        客户问题：thinking.type=disabled 后 reasoning_tokens 仍=100/75、
        reasoning_content 照常输出，关思考相关功能（低延迟模式、关思考
        温度档）全部失效。官方端点实测（官方 FAQ 与实测不符，以实测
        为准）：disabled 后思考完全关闭——reasoning_tokens 为空、无
        reasoning_content、正文正常返回；客户网关对 disabled 不响应
        （rt 仍>0），与官方实测不一致。
        本用例输入保持客户原值 thinking={"type": "disabled"}、显式
        temperature=0.6（官方关思考档唯一合法温度，契约见 K6；不传
        max_tokens），连发 3 次（消息各异、相邻间隔 3s），断言每次均
        按官方实测预期：
        - 无思考内容（reasoning_content/reasoning 均为空）
        - reasoning_tokens 为空（0/缺失；兼容 usage.reasoning_tokens 与
          completion_tokens_details.reasoning_tokens 两种拼写）
        - 正文正常返回且 finish_reason 自然结束
        任一次不符合即失败，并报告第几次。
        """
        # K5: 客户原始请求的思考开关参数——thinking.type=disabled（与 K1
        # 的 enabled 为同一参数面）。官方端点实测（官方 FAQ 与实测不符，
        # 以实测为准）：disabled 后思考完全关闭——reasoning_tokens 为空
        # （0/缺失）、无 reasoning_content、正文正常返回。客户网关对
        # disabled 不响应（reasoning_tokens 仍 >0、reasoning_content 照常
        # 输出）。
        K5_THINKING_DISABLED = {"type": "disabled"}

        # K5: 官方关思考档唯一合法温度——disabled 下给 1 或 0 会被 400
        # 拒绝（"only 0.6 is allowed for this model in non-thinking mode"，
        # 官方契约见 K6），显式指定 0.6 与官方关思考用法对齐
        K5_TEMPERATURE = 0.6

        # K5: 3 个不同的用户提示词（客户原始 prompt 未提供；消息各异 +
        # 3s 间隔，沿用 K4 模式：3 次全部符合官方实测预期才通过，任一次
        # 失败报告第几次）
        K5_USER_PROMPTS = (
            "请用一句话解释什么是通货膨胀。",
            "请把'今天天气很好'翻译成英文。",
            "请列出三种常见的颜色，用顿号分隔。",
        )

        # K5: 相邻两次请求的间隔（秒）——第 1、2 次完成后间隔 3s 再发起
        # 下一次（末次后不等待）
        K5_REQUEST_INTERVAL_SECONDS = 3

        # K5: 官方实测预期下的自然结束原因（未传 max_tokens，正常生成
        # 自然停止）
        K5_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - thinking.type=disabled 后思考未关闭"
            f"（连发 {len(K5_USER_PROMPTS)} 次，消息各异）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_request(index: int, prompt: str) -> None:
            """K5 单次请求核心逻辑：thinking.type=disabled，按官方实测预期断言

            任一步失败即判失败并报告第 {index}/{len(K5_USER_PROMPTS)} 次。
            """
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "thinking": "disabled（客户原始请求参数）",
                    "temperature": "0.6（官方关思考档唯一合法温度）",
                    "max_tokens": "未传（客户原始请求）",
                    "stream": False,
                    "request": f"第 {index}/{len(K5_USER_PROMPTS)} 次（消息各异）",
                },
            )

            # 客户请求形态：model/messages/thinking(disabled)/temperature=0.6，
            # 不带 max_tokens。手工构造 payload 直发（K3/K4 先例），保持客户
            # 原始参数面
            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "thinking": K5_THINKING_DISABLED,
                "temperature": K5_TEMPERATURE,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(url, payload, stream=False)
            except Exception as e:
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次请求发送异常"
                    f"（{url}）: {e}"
                )
            elapsed = time.time() - started

            if response.status_code != 200:
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次请求失败 "
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )

            choices = result.get("choices") or []
            assert choices, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            choice = choices[0]
            message = choice.get("message") or {}
            content = (message.get("content") or "").strip()
            finish_reason = choice.get("finish_reason")
            usage = result.get("usage") or {}

            # 思考内容字段名兼容：reasoning_content（Kimi/Zhipu/DeepSeek
            # 风格）与 reasoning（部分网关）
            reasoning_text = ""
            for field in ("reasoning_content", "reasoning"):
                value = message.get(field)
                if isinstance(value, str):
                    reasoning_text += value

            # reasoning_tokens 字段名兼容：usage.reasoning_tokens（Kimi/
            # Zhipu 风格）与 usage.completion_tokens_details.reasoning_tokens
            # （OpenAI 风格）
            details = usage.get("completion_tokens_details") or {}
            reasoning_tokens = 0
            for value in (
                usage.get("reasoning_tokens"),
                details.get("reasoning_tokens"),
            ):
                if isinstance(value, (int, float)) and value > 0:
                    reasoning_tokens = int(value)
                    break

            # 核心断言 1：官方实测——disabled 后无思考内容
            assert not reasoning_text.strip(), (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后仍返回思考内容（官方实测应无 "
                f"reasoning_content），思考内容长度 {len(reasoning_text)}，"
                f"预览: {reasoning_text[:60]}，消息: {prompt[:30]}"
            )

            # 核心断言 2：官方实测——reasoning_tokens 为空（0/缺失）
            assert reasoning_tokens == 0, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后 reasoning_tokens={reasoning_tokens}"
                f"（官方实测应为空/0），消息: {prompt[:30]}"
            )

            # 核心断言 3：官方实测——正文正常返回
            assert content, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后返回正文为空（官方实测正文应正常"
                f"返回），finish_reason={finish_reason}，消息: {prompt[:30]}"
            )

            # 核心断言 4：自然结束（未传 max_tokens）
            assert finish_reason in K5_NATURAL_FINISH_REASONS, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"finish_reason='{finish_reason}'（期望自然结束 "
                f"{K5_NATURAL_FINISH_REASONS}），消息: {prompt[:30]}"
            )

            # 软观察：usage 缺失时告警（无法观测 reasoning_tokens）
            if not usage:
                test_logger.warning(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次响应未携带 usage，"
                    "无法观测 reasoning_tokens（缺失视为'为空'）"
                )

            TestLogger.log_response(
                test_logger, result, f"K5-响应（第 {index} 次）"
            )
            test_logger.info(
                f"第 {index}/{len(K5_USER_PROMPTS)} 次正常（thinking 已关闭）: "
                f"finish_reason={finish_reason}, reasoning_tokens="
                f"{reasoning_tokens}, 思考内容长度={len(reasoning_text)}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"耗时 {elapsed:.1f}s, 消息: {prompt[:30]}"
            )

        for i, prompt in enumerate(K5_USER_PROMPTS, start=1):
            run_request(i, prompt)
            # 相邻请求间隔（末次后不等待）
            if i < len(K5_USER_PROMPTS):
                time.sleep(K5_REQUEST_INTERVAL_SECONDS)

        test_logger.info(
            "客户问题复现通过: thinking.type=disabled 已生效，连发 "
            f"{len(K5_USER_PROMPTS)} 次（消息各异）均无思考内容、"
            "reasoning_tokens 为空、正文正常返回"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_thinking_temperature_tier(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K6 [P0]: 客户问题 - 关思考温度档未联动校验

        官方契约（kimi-k3 官方说明）：thinking 模式与 temperature 档位
        联动校验——
        - disabled + temperature=0.6：合法，200 正常返回
        - disabled + temperature=1 或 0：非法，400 拒绝并报
          "only 0.6 is allowed for this model in non-thinking mode"
        - enabled + temperature=1：合法，200 正常返回
        - enabled + temperature=0.6 或 0：非法，400 拒绝并报
          "only 1 is allowed for this model in thinking mode"
        客户影响：关思考相关功能（低延迟模式、关思考温度档）全部失效
        （K5 验证关思考本身，本用例验证温度档联动校验）。
        本用例对 6 个组合各发一次请求（参数校验为确定性行为，无需
        K4/K5 式多次连发），断言：
        - 合法组合：HTTP 200 + 正文非空
        - 非法组合：HTTP 400 + 错误信息包含官方文案（忽略大小写子串
          匹配，对错误体的 JSON 结构不敏感）
        任一组合不符合即失败，并报告具体场景。
        """
        # K6: 客户原始 user 提示词——6 个场景复用同一提示词，仅 thinking
        # 与 temperature 参数变化（参数联动校验与 prompt 内容无关，同一
        # prompt 使各场景唯一变量为被测参数）
        K6_USER_PROMPT = "请用一句话介绍你自己。"

        # K6: 关思考温度档——官方契约（kimi-k3 官方说明）：thinking 模式
        # 与 temperature 档位联动校验，合法组合 200 正常返回，非法组合
        # 400 拒绝并报对应错误信息：
        # - disabled + temperature=0.6：合法（关思考档唯一合法温度）
        # - disabled + temperature=1 或 0：400
        #   "only 0.6 is allowed for this model in non-thinking mode"
        # - enabled + temperature=1：合法（开思考档唯一合法温度）
        # - enabled + temperature=0.6 或 0：400
        #   "only 1 is allowed for this model in thinking mode"
        K6_SCENARIOS = (
            {
                "label": "disabled+temp=0.6（合法）",
                "thinking": {"type": "disabled"},
                "temperature": 0.6,
                "expect_ok": True,
                "error_substring": None,
            },
            {
                "label": "disabled+temp=1（非法）",
                "thinking": {"type": "disabled"},
                "temperature": 1,
                "expect_ok": False,
                "error_substring": (
                    "only 0.6 is allowed for this model in non-thinking mode"
                ),
            },
            {
                "label": "disabled+temp=0（非法）",
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "expect_ok": False,
                "error_substring": (
                    "only 0.6 is allowed for this model in non-thinking mode"
                ),
            },
            {
                "label": "enabled+temp=1（合法）",
                "thinking": {"type": "enabled"},
                "temperature": 1,
                "expect_ok": True,
                "error_substring": None,
            },
            {
                "label": "enabled+temp=0.6（非法）",
                "thinking": {"type": "enabled"},
                "temperature": 0.6,
                "expect_ok": False,
                "error_substring": (
                    "only 1 is allowed for this model in thinking mode"
                ),
            },
            {
                "label": "enabled+temp=0（非法）",
                "thinking": {"type": "enabled"},
                "temperature": 0,
                "expect_ok": False,
                "error_substring": (
                    "only 1 is allowed for this model in thinking mode"
                ),
            },
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - 关思考温度档未联动校验"
            f"（{len(K6_SCENARIOS)} 个组合）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_scenario(scenario: Dict[str, Any]) -> None:
            """K6 单场景核心逻辑：thinking 模式 × temperature 档位联动校验

            合法组合断言 200+正文非空；非法组合断言 400+官方错误文案。
            """
            label = scenario["label"]
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K6_USER_PROMPT}],
                {
                    "thinking": scenario["thinking"]["type"],
                    "temperature": scenario["temperature"],
                    "max_tokens": "未传（契约校验与生成长度无关）",
                    "stream": False,
                    "scenario": label,
                },
            )

            # 官方契约校验场景：thinking 与 temperature 为被测参数，其余
            # 保持最小参数面（手工构造 payload 直发，K3/K4/K5 先例）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K6_USER_PROMPT}],
                "thinking": scenario["thinking"],
                "temperature": scenario["temperature"],
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(url, payload, stream=False)
            except Exception as e:
                pytest.fail(f"场景[{label}] 请求发送异常（{url}）: {e}")

            if scenario["expect_ok"]:
                # 合法组合：官方契约应 200 正常返回
                assert response.status_code == 200, (
                    f"场景[{label}] 客户问题复现失败：官方契约为合法组合，"
                    f"应 200 正常返回，实际 HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
                try:
                    result = response.json()
                except (json.JSONDecodeError, ValueError) as e:
                    pytest.fail(
                        f"场景[{label}] 响应不是合法 JSON: {e}. "
                        f"响应体: {response.text[:300]}"
                    )
                choices = result.get("choices") or []
                assert choices, (
                    f"场景[{label}] 响应缺少 choices: "
                    f"{json.dumps(result, ensure_ascii=False)[:500]}"
                )
                content = (
                    (choices[0].get("message") or {}).get("content") or ""
                ).strip()
                # 合法组合应正常生成正文（enabled 场景可能含
                # reasoning_content，属正常思考输出，不在本用例断言范围
                # ——关思考本身由 K5 验证）
                assert content, (
                    f"场景[{label}] 客户问题复现失败：合法组合应正常返回正文，"
                    f"实际正文为空: {json.dumps(result, ensure_ascii=False)[:300]}"
                )
                TestLogger.log_response(
                    test_logger, result, f"K6-响应（{label}）"
                )
                test_logger.info(
                    f"场景[{label}] 正常: HTTP 200, 正文长度 {len(content)}, "
                    f"completion_tokens="
                    f"{(result.get('usage') or {}).get('completion_tokens')}"
                )
            else:
                # 非法组合：官方契约应 400 拒绝并报对应文案
                expected_msg = scenario["error_substring"]
                assert response.status_code == 400, (
                    f"场景[{label}] 客户问题复现失败：官方契约应 400 拒绝"
                    f"（错误信息含 '{expected_msg}'），实际 HTTP "
                    f"{response.status_code}: {response.text[:300]}"
                )
                # 错误文案校验：忽略大小写的子串匹配（对错误体的 JSON 结构
                # 不敏感——官方文案可能嵌在 error.message 等不同位置）
                assert expected_msg.lower() in response.text.lower(), (
                    f"场景[{label}] 客户问题复现失败：400 错误信息与官方不一致，"
                    f"期望包含 '{expected_msg}'，实际: {response.text[:300]}"
                )
                test_logger.info(
                    f"场景[{label}] 正常拒绝: HTTP 400, 错误信息含官方文案 "
                    f"'{expected_msg}'"
                )

        for scenario in K6_SCENARIOS:
            run_scenario(scenario)

        test_logger.info(
            "客户问题复现通过: thinking 模式与温度档联动校验与官方契约一致"
            f"（{len(K6_SCENARIOS)} 个组合全部符合）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p0
    def test_thinking_effort_reasoning_length(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """K7 [P0]: 客户问题 - 思考强度档位思考长度倒挂（官方 reasoning_effort）

        官方契约（kimi-k3 官方文档 use-reasoning-effort /
        kimi-k3-quickstart）：思考强度为顶层 reasoning_effort 参数
        （K2.x 的 thinking 配置在 K3 已废弃，官方迁移指引为移除
        thinking 改用顶层 reasoning_effort），K3 恒开思考；官方预期
        思考长度（reasoning_tokens）随档位递增。
        本用例只按官方格式传参（顶层 reasoning_effort，无回退），
        请求顺序（客户指定）：low → high → max 后比对思考长度，
        再按 max → high → low 逆向重发并再次比对思考长度——正逆
        两轮排除请求顺序相关干扰（缓存/预热），均按 low < high <
        max 三档软对比（medium 不参与对比）；最后依次验证 medium
        顶层（按官方预期 200 放行）与 medium 嵌套
        （thinking.effort=medium 预期 400——废弃的 K2.x thinking
        配置下 medium 为非法档位，客户指定契约）。
        请求内容与 temperature 完全相同（temperature=1，开思考档
        契约温度，见 K6），相邻间隔 3s。
        断言（硬）——请求基本健康，否则长度对比无意义：
        - 每次官方档请求（升序轮+降序轮+medium 顶层）HTTP 200 +
          正文非空 + finish_reason 自然结束
        - 嵌套 thinking.effort=medium 预期 HTTP 400
        对比（软，按客户要求倒挂不判失败，仅告警）：
        - low 与 high、high 与 max 的 reasoning_tokens 应严格递增；
          任一对倒挂/持平 → 告警记入报告，用例仍通过（档位倒挂属
          行为质量偏离而非服务故障）
        - 三档均为 0 → 告警思考强度参数可能未生效
        reasoning_tokens 兼容两种字段拼写（K5 先例）；usage 缺失时
        逐次软告警（K5 先例）。
        """
        # K7: 升序轮发送顺序——low → high → max，发送后比对思考长度
        K7_ASCENDING_LEVELS = ("low", "high", "max")

        # K7: 降序轮发送顺序——max → high → low，逆向重发后再比对
        # 思考长度（正逆两轮排除请求顺序相关干扰：缓存/预热）
        K7_DESCENDING_LEVELS = ("max", "high", "low")

        # K7: 参与思考长度对比的档位（两轮共用）——medium 为合法
        # 档位但不参与对比（对比仍按 low < high < max 严格递增）
        K7_COMPARISON_LEVELS = ("low", "high", "max")

        # K7: 请求总数——升序轮 3 + 降序轮 3 + medium 顶层 1 +
        # medium 嵌套 1
        K7_TOTAL_REQUESTS = (
            len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS) + 2
        )

        # K7: 嵌套 thinking.effort=medium——废弃的 K2.x thinking 配置
        # 下 medium 为非法档位，预期 400（客户指定契约）
        K7_NESTED_MEDIUM = {"type": "enabled", "effort": "medium"}

        # K7: 客户原始 user 提示词——需要逐步推理的问题，使各档思考
        # 长度差异可观测；各档请求内容完全相同（仅思考强度不同）
        K7_USER_PROMPT = (
            "一个笼子里有鸡和兔共 35 个头、94 只脚，请问鸡和兔各有多少只？"
            "请逐步推理后给出答案。"
        )

        # K7: 开思考档契约温度（K6；官方文档 K3 temperature 固定
        # 1.0），各档相同
        K7_TEMPERATURE = 1

        # K7: 相邻两次请求的间隔（秒）——K2/K4/K5 先例（末次后
        # 不等待）
        K7_REQUEST_INTERVAL_SECONDS = 3

        # K7: 自然结束原因（不传 max_tokens，观察思考自然长度，
        # K4/K5 先例）
        K7_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - 思考强度档位思考长度对比"
            "（官方顶层 reasoning_effort；low→high→max 比对后 "
            "max→high→low 再比对；最后 medium 顶层 200 放行、"
            "medium 嵌套 400；倒挂仅告警不判失败）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"
        messages = [{"role": "user", "content": K7_USER_PROMPT}]

        def run_official_request(index: int, effort: str) -> Dict[str, Any]:
            """K7 官方格式单次请求：顶层 reasoning_effort={effort}

            硬断言响应基本健康（200+正文非空+自然结束），返回观测到的
            reasoning_tokens（双拼写兼容，缺失按 0）与思考文本长度。
            """
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "reasoning_effort": effort,
                    "temperature": K7_TEMPERATURE,
                    "max_tokens": "未传（观察思考自然长度）",
                    "stream": False,
                    "round": f"第{index}次/{K7_TOTAL_REQUESTS}",
                },
            )

            # 思考强度为唯一被测参数，其余保持最小参数面（手工构造
            # payload 直发，K3-K6 先例）
            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "reasoning_effort": effort,
                "temperature": K7_TEMPERATURE,
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"第[{index}]次（reasoning_effort={effort}）请求发送"
                    f"异常（{url}）: {e}"
                )

            assert response.status_code == 200, (
                f"第[{index}]次（reasoning_effort={effort}）请求失败："
                f"应 200 正常返回，实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第[{index}]次（reasoning_effort={effort}）响应不是"
                    f"合法 JSON: {e}. 响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"第[{index}]次（reasoning_effort={effort}）响应缺少 "
                f"choices: {json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = (message.get("content") or "").strip()
            assert content, (
                f"第[{index}]次（reasoning_effort={effort}）正文为空: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            finish_reason = (choices[0].get("finish_reason") or "").lower()
            assert finish_reason in K7_NATURAL_FINISH_REASONS, (
                f"第[{index}]次（reasoning_effort={effort}）finish_reason "
                f"异常: '{finish_reason}'（预期自然结束，未传 "
                f"max_tokens）"
            )

            # 思考长度观测（软指标，不参与硬断言）：reasoning_tokens
            # 双拼写兼容（K5 先例）
            usage = result.get("usage") or {}
            if not usage:
                # usage 缺失不影响请求健康判定，仅软告警（K5 先例）
                warn_msg = (
                    f"第[{index}]次（reasoning_effort={effort}）响应缺少 "
                    "usage，无法观测思考长度"
                )
                test_logger.warning(f"[K7-警告] {warn_msg}")
                record_warning(warn_msg)
            reasoning_tokens = usage.get("reasoning_tokens")
            if reasoning_tokens is None:
                details = usage.get("completion_tokens_details") or {}
                reasoning_tokens = details.get("reasoning_tokens")
            reasoning_tokens = reasoning_tokens or 0
            reasoning_text = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or ""
            )

            TestLogger.log_response(
                test_logger,
                result,
                f"K7-响应（reasoning_effort={effort}）",
            )
            test_logger.info(
                f"第[{index}]次（reasoning_effort={effort}）正常: "
                f"HTTP 200, reasoning_tokens={reasoning_tokens}, "
                f"思考文本长度={len(reasoning_text)}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"正文长度={len(content)}, finish_reason={finish_reason}"
            )
            return {
                "effort": effort,
                "reasoning_tokens": reasoning_tokens,
                "reasoning_len": len(reasoning_text),
            }

        def run_nested_medium_reject(index: int) -> None:
            """K7 嵌套 thinking.effort=medium：预期 400

            废弃的 K2.x thinking 配置下 medium 为非法档位，按客户
            指定契约预期 400 拒绝。
            """
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "thinking": K7_NESTED_MEDIUM,
                    "temperature": K7_TEMPERATURE,
                    "max_tokens": "未传（契约校验与生成长度无关）",
                    "stream": False,
                    "round": f"第{index}次",
                    "expect": "reject",
                },
            )

            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "thinking": K7_NESTED_MEDIUM,
                "temperature": K7_TEMPERATURE,
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"第[{index}]次（嵌套 thinking.effort=medium）请求"
                    f"发送异常（{url}）: {e}"
                )

            assert response.status_code == 400, (
                f"第[{index}]次（嵌套 thinking.effort=medium）预期 400 "
                f"拒绝（废弃的 K2.x thinking 配置下 medium 为非法"
                f"档位），实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            test_logger.info(
                f"第[{index}]次（嵌套 thinking.effort=medium）按预期"
                f"拒绝: HTTP 400: {response.text[:200]}"
            )

        def compare_pass(
            pass_label: str, observations: Dict[str, Dict[str, Any]]
        ) -> str:
            """K7 单轮思考长度软对比（low < high < max）

            倒挂/持平仅告警不判失败（客户要求：行为质量偏离而非
            服务故障），返回本轮观测摘要。
            """
            rt = {
                level: observations[level]["reasoning_tokens"]
                for level in K7_COMPARISON_LEVELS
            }
            rt_low, rt_high, rt_max = rt["low"], rt["high"], rt["max"]
            summary = (
                f"{pass_label}思考长度观测: low={rt_low}, "
                f"high={rt_high}, max={rt_max}"
            )
            if rt_low == 0 and rt_high == 0 and rt_max == 0:
                # 全 0：无法区分"思考强度未生效/思考未开启"与"未上报
                # 思考 tokens"
                warn_msg = (
                    f"{summary}——对比三档均为 0，思考强度参数可能"
                    "未生效或服务端未上报思考 tokens，无法进行档位对比"
                )
                test_logger.warning(f"[K7-警告] {warn_msg}")
                record_warning(warn_msg)
            else:
                inversion_found = False
                if rt_low >= rt_high:
                    warn_msg = (
                        f"{summary}——档位倒挂/持平: low({rt_low}) 未小于 "
                        f"high({rt_high})，官方预期 low < high < max"
                    )
                    test_logger.warning(f"[K7-警告] {warn_msg}")
                    record_warning(warn_msg)
                    inversion_found = True
                if rt_high >= rt_max:
                    warn_msg = (
                        f"{summary}——档位倒挂/持平: high({rt_high}) 未小于 "
                        f"max({rt_max})，官方预期 low < high < max"
                    )
                    test_logger.warning(f"[K7-警告] {warn_msg}")
                    record_warning(warn_msg)
                    inversion_found = True
                if inversion_found:
                    test_logger.warning(
                        "[K7-警告] 检测到思考强度档位思考长度未严格递增"
                        "（按约定不判失败，请检查思考强度档位到后端思考"
                        "预算的映射）"
                    )
                else:
                    test_logger.info(
                        f"{summary}，档位严格递增，符合官方预期"
                    )
            return summary

        # === 升序轮：low → high → max，发送后比对思考长度 ===
        observations: Dict[str, Dict[str, Any]] = {}
        for index, effort in enumerate(K7_ASCENDING_LEVELS, start=1):
            observations[effort] = run_official_request(index, effort)
            if index < len(K7_ASCENDING_LEVELS):
                time.sleep(K7_REQUEST_INTERVAL_SECONDS)
        summary_asc = compare_pass("升序轮（low→high→max）", observations)

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === 降序轮：max → high → low，逆向重发后再比对思考长度 ===
        observations_desc: Dict[str, Dict[str, Any]] = {}
        for index, effort in enumerate(
            K7_DESCENDING_LEVELS, start=len(K7_ASCENDING_LEVELS) + 1
        ):
            observations_desc[effort] = run_official_request(index, effort)
            if index < len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS):
                time.sleep(K7_REQUEST_INTERVAL_SECONDS)
        summary_desc = compare_pass(
            "降序轮（max→high→low）", observations_desc
        )

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === medium 顶层：合法档位，按官方预期 200 放行（不参与对比） ===
        medium_index = (
            len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS) + 1
        )
        medium_observation = run_official_request(medium_index, "medium")

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === 最后：medium 嵌套 thinking.effort=medium 预期 400
        # （客户指定契约） ===
        run_nested_medium_reject(medium_index + 1)

        test_logger.info(
            "客户问题复现通过: 升序/降序两轮思考强度请求均正常返回，"
            "medium 顶层按官方放行、medium 嵌套按预期拒绝"
            f"（思考长度对比仅告警不判失败；{summary_asc}；"
            f"{summary_desc}；medium 顶层 reasoning_tokens="
            f"{medium_observation['reasoning_tokens']}，"
            "合法档位不参与对比）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p1
    def test_required_chitchat_calls_tool(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K8 [P1]: 客户问题 - required+闲聊必须调用工具（客户工单级别，finish=tool_calls、预算不被吃满）

        客户工单原始问题：tool_choice=required + 闲聊
        "Reply with exactly: OK"（无工具意图）下不发起工具调用：
        tool_calls 键缺失、finish=length、completion_tokens 恒被
        吃满 max_tokens（关思考 1000/3000 级别均如此）、正文仅
        "OK"、耗时 ~15.6s（正常 ~1.5s，双峰）；开思考下
        reasoning 消耗远小于预算但整体仍被吃满（mt=3000 仍不调）。
        预期（工单）：required 必须发起工具调用——finish 应为
        tool_calls 而非 length；关思考 ct 应较小、耗时应较少；
        开思考 rt 应 < max_tokens；正文应正常收到调用工具的响应
        信息。
        轮次（客户实测级别）：关思考 mt=1000、关思考 mt=3000、
        开思考 mt=3000；工具定义 get_weather(city)（获取北京天气
        的工具，city 值不限定）。temperature 按网关档位联动约束
        取 disabled→0.6 / enabled→1（非该值被 400 拒绝，无法构
        建场景）。每轮硬断言：
        - HTTP 200 + choices + usage 存在（ct 判定数据源）
        - tool_calls 存在且为 get_weather 函数调用，arguments 为
          合法 JSON
        - finish_reason == "tool_calls"（而非 length——length 即
          token 预算被消耗殆尽的缺陷形态，关/开思考均不允许）
        - ct < max_tokens（关思考下应较小；缺陷形态为恒吃满）
        - 开思考：rt（reasoning tokens）< max_tokens（思考不吃完
          预算）；rt 双拼写兼容
        耗时双峰（缺陷 15.6s 级 vs 正常 1.5s 级）仅日志留痕——
        finish 断言已覆盖其缺陷形态，不对绝对耗时硬断言（网络抖
        动易误报）。官方行为对照级别（mt=256/2000）由 K9 验证。
        （不进 smoke 集：缺陷轮 15.6s 级长耗时+缺陷概率性）
        """
        # K8: 工具定义——获取北京天气（get_weather(city)，客户工单
        # 原始工具）
        K8_TOOLS = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]

        # K8: 闲聊提示词（客户原始口径）——无工具意图 + required 即
        # 缺陷触发条件
        K8_USER_PROMPT = "Reply with exactly: OK"

        # K8: 轮次（标签, thinking, temperature, max_tokens）——按客户
        # 实测级别：关思考 mt=1000/3000、开思考 mt=3000；temperature
        # 按网关档位联动约束（disabled→0.6、enabled→1，非该值被
        # 400 拒绝、无法构建场景）
        K8_ROUNDS = (
            ("关思考 mt=1000", "disabled", 0.6, 1000),
            ("关思考 mt=3000", "disabled", 0.6, 3000),
            ("开思考 mt=3000", "enabled", 1, 3000),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - required+闲聊必须调用工具"
            f"（{K8_USER_PROMPT}；关思考 mt=1000/3000、开思考 "
            "mt=3000；断言 tool_calls+finish=tool_calls+ct/rt 不被"
            "吃满；官方行为对照级别 256/2000 由 K9 验证）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_round(
            label: str, thinking_type: str, temperature: float,
            max_tokens: int,
        ) -> None:
            """K8 单轮：required+有工具意图，断言必须调用工具且预算不被吃满"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K8_USER_PROMPT}],
                {
                    "tools": [t["function"]["name"] for t in K8_TOOLS],
                    "tool_choice": "required",
                    "thinking": thinking_type,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需 tools/tool_choice/max_tokens/
            # 档位温度，chat_completion 封装会强制覆盖 max_tokens/
            # temperature）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K8_USER_PROMPT}],
                "tools": K8_TOOLS,
                "tool_choice": "required",
                "thinking": {"type": thinking_type},
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回，实际 "
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            ct = usage.get("completion_tokens")
            assert isinstance(ct, int), (
                f"[{label}] 客户问题复现失败：usage 缺少有效 "
                f"completion_tokens: "
                f"{json.dumps(usage, ensure_ascii=False)[:300]}"
            )
            # rt 双拼写兼容；缺失按 None（关思考不强制上报）
            rt = usage.get("reasoning_tokens")
            if rt is None:
                details = usage.get("completion_tokens_details") or {}
                rt = details.get("reasoning_tokens")

            TestLogger.log_response(test_logger, result, f"K8-响应（{label}）")
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, ct={ct}, "
                f"rt={rt}, finish={finish}, "
                f"tool_calls={'有' if tool_calls else '无'}, "
                f"content_len={len(content)}"
            )

            # 断言1：required 必须发起工具调用（缺陷形态：tool_calls
            # 键缺失、正文仅 "OK"、ct 恒吃满预算、finish=length）
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下未发起工具"
                f"调用——tool_calls 键缺失（finish={finish}、ct={ct}/"
                f"{max_tokens}；缺陷形态：finish=length、completion_"
                f"tokens 恒吃满 max_tokens、正文仅 OK）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"{json.dumps(first, ensure_ascii=False)[:200]}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（{fn.get('arguments')!r}）"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象: {fn.get('arguments')!r}"
            )

            # 断言2：finish 必须为 tool_calls（length 即 token 预算
            # 被消耗殆尽的缺陷形态——关/开思考均不允许，断言不分模式）
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}——token 被消耗殆尽"
                f"的缺陷形态）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )

            # 断言3：预算不被吃满（缺陷形态：ct 恒==max_tokens）
            assert ct < max_tokens, (
                f"[{label}] 客户问题复现失败：completion_tokens={ct} "
                f"吃满 max_tokens={max_tokens}——关思考下 ct 应较"
                f"小、不被吃满"
            )

            # 断言4（开思考）：思考消耗应小于 max_tokens
            if thinking_type == "enabled":
                assert isinstance(rt, int) and rt >= 0, (
                    f"[{label}] 客户问题复现失败：开思考下 usage 未上"
                    f"报有效 reasoning_tokens（rt={rt}），无法验证"
                    f"思考消耗 < max_tokens"
                )
                assert rt < max_tokens, (
                    f"[{label}] 客户问题复现失败：reasoning tokens="
                    f"{rt} 吃满/超出 max_tokens={max_tokens}——思考"
                    f"不应吃完预算"
                )

        for label, thinking_type, temperature, max_tokens in K8_ROUNDS:
            run_round(label, thinking_type, temperature, max_tokens)

        test_logger.info(
            "客户问题复现通过: required+闲聊 关思考 mt=1000/3000、"
            "开思考 mt=3000 全部正常发起 get_weather 调用"
            "（finish=tool_calls、ct/rt 均未吃满预算；官方行为对照"
            "级别由 K9 验证）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.p1
    def test_required_chitchat_official_behavior(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K9 [P1]: 客户问题 - required+闲聊必须强制调用工具（按官方行为为预期）

        官方 api.moonshot.cn/kimi-k3 实测：闲聊 "Reply with exactly:
        OK" + required → finish=tool_calls、强制返回 get_weather 调用
        （city 瞎猜 London/UNKNOWN——值不限定）、reasoning 仅 38
        token——符合 [OI] required「必须发起至少一次工具调用」规范。
        Alaya 同场景缺陷：finish=length、reasoning 吃满 256/2000
        预算、tool_calls=None；有工具意图时（北京天气）两站一致
        正常。
        本用例按官方行为为预期（与 K8 同场景不同级别：K8 为客户
        工单级别 mt=1000/3000/3000 复现，本用例镜像 Alaya 缺陷实
        测级别）。轮次：关思考 mt=256、关思考 mt=2000、开思考
        mt=256、开思考 mt=2000。temperature 按网关档位联动约束取
        disabled→0.6 / enabled→1（非该值被 400 拒绝，无法构建场
        景）。每轮硬断言：
        - HTTP 200 + choices + usage 存在
        - tool_calls 强制返回且为 get_weather 函数调用、arguments
          为合法 JSON（city 值不限定——官方亦瞎猜）
        - finish_reason == "tool_calls"（而非 length）
        - ct < max_tokens（预算不被吃满）
        - 开思考：rt < max_tokens（官方 reasoning 仅 38；缺陷形态
          为吃满预算）；rt 双拼写兼容
        耗时双峰仅日志留痕（finish 断言已覆盖缺陷形态，同 K8 理
        由）。（不进 smoke 集：缺陷轮 15.6s 级长耗时 + 缺陷概率性）
        """
        # K9: 工具定义（get_weather(city)）——与 K8 相同的客户原始工
        # 具（各用例独立自包含，不共享常量）
        K9_TOOLS = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]

        # K9: 闲聊提示词（客户原始口径，官方对照同款）——无工具意图
        # + required 即缺陷触发条件
        K9_USER_PROMPT = "Reply with exactly: OK"

        # K9: 轮次（标签, thinking, temperature, max_tokens）——镜像
        # Alaya 缺陷实测级别 256/2000 × 关/开思考；temperature 按网
        # 关档位联动约束
        K9_ROUNDS = (
            ("关思考 mt=256", "disabled", 0.6, 256),
            ("关思考 mt=2000", "disabled", 0.6, 2000),
            ("开思考 mt=256", "enabled", 1, 256),
            ("开思考 mt=2000", "enabled", 1, 2000),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - required+闲聊必须强制调用"
            "工具（'Reply with exactly: OK'；关/开思考 × mt=256/"
            "2000；按官方行为为预期：finish=tool_calls+强制 "
            "get_weather+预算不被吃满；客户工单级别 mt=1000/3000 "
            "由 K8 验证）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_round(
            label: str, thinking_type: str, temperature: float,
            max_tokens: int,
        ) -> None:
            """K9 单轮：required+闲聊，断言必须强制调用工具且预算不被吃满"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K9_USER_PROMPT}],
                {
                    "tools": [t["function"]["name"] for t in K9_TOOLS],
                    "tool_choice": "required",
                    "thinking": thinking_type,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需 tools/tool_choice/max_tokens/
            # 档位温度，chat_completion 封装会强制覆盖 max_tokens/
            # temperature）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K9_USER_PROMPT}],
                "tools": K9_TOOLS,
                "tool_choice": "required",
                "thinking": {"type": thinking_type},
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回，实际 "
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            ct = usage.get("completion_tokens")
            assert isinstance(ct, int), (
                f"[{label}] 客户问题复现失败：usage 缺少有效 "
                f"completion_tokens: "
                f"{json.dumps(usage, ensure_ascii=False)[:300]}"
            )
            # rt 双拼写兼容；缺失按 None（关思考不强制上报）
            rt = usage.get("reasoning_tokens")
            if rt is None:
                details = usage.get("completion_tokens_details") or {}
                rt = details.get("reasoning_tokens")

            TestLogger.log_response(test_logger, result, f"K9-响应（{label}）")
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, ct={ct}, "
                f"rt={rt}, finish={finish}, "
                f"tool_calls={'有' if tool_calls else '无'}, "
                f"content_len={len(content)}"
            )

            # 断言1：required 必须强制发起工具调用（官方行为：闲聊也
            # 强制返回 get_weather，city 瞎猜不限定；Alaya 缺陷形态：
            # tool_calls=None、finish=length、reasoning 吃满预算）
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下闲聊未强制"
                f"发起工具调用——tool_calls 键缺失（finish={finish}、"
                f"ct={ct}/{max_tokens}；官方行为为 finish=tool_calls"
                f" 强制返回 get_weather，Alaya 缺陷形态为 finish="
                f"length、reasoning 吃满预算、tool_calls=None）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"{json.dumps(first, ensure_ascii=False)[:200]}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（{fn.get('arguments')!r}）"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象: {fn.get('arguments')!r}"
            )

            # 断言2：finish 必须为 tool_calls（官方行为；而非 length）
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )

            # 断言3：预算不被吃满（Alaya 缺陷形态：ct 恒吃满预算）
            assert ct < max_tokens, (
                f"[{label}] 客户问题复现失败：completion_tokens={ct} "
                f"吃满 max_tokens={max_tokens}——预算不应被吃满"
            )

            # 断言4（开思考）：思考消耗应小于 max_tokens
            if thinking_type == "enabled":
                assert isinstance(rt, int) and rt >= 0, (
                    f"[{label}] 客户问题复现失败：开思考下 usage 未上"
                    f"报有效 reasoning_tokens（rt={rt}），无法验证"
                    f"思考消耗 < max_tokens"
                )
                assert rt < max_tokens, (
                    f"[{label}] 客户问题复现失败：reasoning tokens="
                    f"{rt} 吃满/超出 max_tokens={max_tokens}——思考"
                    f"不应吃完预算（官方同场景 reasoning 仅 38）"
                )

        for label, thinking_type, temperature, max_tokens in K9_ROUNDS:
            run_round(label, thinking_type, temperature, max_tokens)

        test_logger.info(
            "客户问题复现通过: required+闲聊 关/开思考 × mt=256/2000 "
            "全部按官方行为强制返回 get_weather 调用（finish="
            "tool_calls、ct/rt 均未吃满预算；客户工单级别由 K8 验证）"
        )

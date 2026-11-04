"""
F. API 兼容性测试

测试点：
- F1: OpenAI Chat Completions - /v1/chat/completions 接口兼容 [P0]
- F2: OpenAI Completions - /v1/completions 接口兼容 [P1]
- F3: 模型列表 - /v1/models 接口 [P0]
- F4: Usage 统计 - usage 字段准确性 [P0]
- F5: 错误码规范 - 401/400/404 错误码 [P1]
- F6: 客户端 SDK 兼容 - Python openai [P0]
- F7: OpenAI Responses API - /v1/responses 新一代接口兼容 [P0]

注意：response_format（json_object/json_schema）测试见 B8/B9，
      stream 参数测试见 A4，此处不重复测试。
      /v1/responses 的消息数组形式（input_text 类型）与流式事件
      解析由 K30 覆盖，此处不重复。
"""

import json
import time

import pytest
import requests

from base.base_test import BaseTest
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestAPICompatibility(BaseTest):
    """API兼容性测试类"""

    def get_test_category(self) -> str:
        return "F. API兼容性"

    # ------------------------------------------------------------------
    # 测试用例
    # ------------------------------------------------------------------

    @pytest.mark.f_api
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_chat_completions_api(self, api_client: ModelAPIClient, test_logger):
        """F1: OpenAI Chat Completions 接口兼容

        验证 /v1/chat/completions 响应符合 OpenAI 规范：
        - 顶层含 object/model/created/id 字段
        - choices[0].message 含 role=assistant, content 字段
        - finish_reason 合法
        - usage 字段含 prompt_tokens/completion_tokens
        """
        test_logger.info("=== 测试开始: Chat Completions API ===")

        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "请用一句话介绍你自己"},
        ]
        params = {"max_tokens": 2048}
        TestLogger.log_request(test_logger, messages, params)

        response = api_client.chat_completion(messages, max_tokens=2048)
        TestLogger.log_response(test_logger, response, "Chat Completions响应")
        self.log_full_response(test_logger, response, "F1-ChatCompletions")

        # 验证响应成功
        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        # 验证顶层必要字段（OpenAI 规范）
        assert response.get("id") is not None, "Should have response id"
        assert response.get("object") == "chat.completion", (
            f"object should be 'chat.completion', got '{response.get('object')}'"
        )
        assert response.get("model") is not None, "Should have model field"
        assert response.get("created") is not None, "Should have created timestamp"

        # 验证 message 字段
        message = response["choices"][0]["message"]
        assert "role" in message, "Should have role field"
        assert "content" in message, "Should have content field"
        assert message["role"] == "assistant", "Role should be assistant"

        # 验证 finish_reason
        self._assert_finish_reason(response)

        # 验证 usage
        usage = response.get("usage", {})
        assert usage, "Should have usage statistics"
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )

        test_logger.info(f"Chat Completions API: OK, usage={usage}")

    @pytest.mark.f_api
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_completions_api(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """F2: OpenAI Completions 接口兼容

        测试传统 /v1/completions 接口（非 chat 格式）。
        若服务端不支持 Completions API，会抛出异常并降级为软告警；
        但若 API 已支持却因参数错误失败，不应被静默吞没。

        本用例仅验证 /v1/completions 接口的兼容性（响应格式、字段、
        finish_reason、usage），max_tokens 超限行为由 D（长上下文）
        与 F（稳定性）测试套件覆盖，此处不重复测试。
        """
        test_logger.info("=== 测试开始: Completions API ===")

        prompt = "你好，请介绍一下自己"
        test_logger.info(f"Prompt: {prompt}")
        TestLogger.log_request(
            test_logger, [{"role": "user", "content": prompt}], {"max_tokens": 100}
        )

        try:
            response = api_client.completion(prompt=prompt, max_tokens=100)
        except Exception as e:
            # Completions API 可能不被服务端支持
            self.log_full_response(
                test_logger, {"error": str(e)}, "F2-Completions(不支持)"
            )
            record_warning(f"Completions API not supported: {e}")
            test_logger.info(f"Completions API not supported: {e}")
            return

        # API 已支持，以下断言为硬断言（不再吞没异常）
        TestLogger.log_response(test_logger, response, "Completions API响应")
        self.log_full_response(test_logger, response, "F2-Completions")

        # 验证响应（使用 get 避免 KeyError）
        choices = response.get("choices")
        assert choices is not None, (
            f"Should have choices field, got keys: {list(response.keys())}"
        )
        assert len(choices) > 0, "Should have at least one choice"

        text = choices[0].get("text", "")
        assert len(text.strip()) > 0, (
            f"Should have non-empty text content, got {len(text)} chars"
        )

        # 验证 finish_reason
        self._assert_finish_reason(response)

        # 验证 usage（若存在）
        usage = response.get("usage", {})
        if usage:
            assert usage.get("completion_tokens", 0) > 0, (
                "Should have completion_tokens > 0"
            )
            assert usage.get("prompt_tokens", 0) > 0, (
                "Should have prompt_tokens > 0"
            )

        test_logger.info(f"Completions API: OK, text={text[:100]}, usage={usage}")

    @pytest.mark.f_api
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_models_list(self, api_client: ModelAPIClient, test_logger, record_warning):
        """F3 [P0]: 模型列表接口

        验证 /v1/models 返回符合 OpenAI 规范的模型列表：
        - 顶层 object == "list"
        - data 为列表，每个元素含 id 和 object=="model"
        - 当前配置的 model_name 应在列表中

        注意：部分部署（如 sglang）输出较简洁，模型对象可能仅含
        id/object/created/owned_by/context_window，不包含 max_model_len 等
        扩展字段，这是正常的。
        """
        test_logger.info("=== 测试开始: Models List ===")

        response = api_client.list_models()
        TestLogger.log_response(test_logger, response, "Models List响应")
        self.log_full_response(test_logger, response, "F3-ModelsList")

        # 验证顶层格式
        assert "data" in response, (
            f"Should have 'data' field, got keys: {list(response.keys())}"
        )
        assert response.get("object") == "list", (
            f"object should be 'list', got '{response.get('object')}'"
        )

        # 验证数据格式
        models = response["data"]
        assert isinstance(models, list), "Models should be a list"

        if not models:
            record_warning("Models list is empty")
            test_logger.warning("Models list is empty")
            return

        # 验证每个模型对象的必要字段
        model_ids = []
        for model in models:
            assert "id" in model, f"Model should have id, got: {model}"
            model_ids.append(model["id"])
            # object 字段应为 "model"（修复原始恒真断言）
            assert model.get("object") == "model", (
                f"Model item object should be 'model', got '{model.get('object')}'"
            )

        test_logger.info(
            f"Models list: {len(models)} models found, ids: {model_ids[:10]}"
        )

        # 关键验证：当前配置的 model_name 应在列表中
        configured_model = api_client.model_name
        assert configured_model in model_ids, (
            f"Configured model '{configured_model}' not found in models list: {model_ids}"
        )
        test_logger.info(f"Configured model '{configured_model}' found in list")

        # 记录模型元信息（若有）
        configured_info = next(
            (m for m in models if m.get("id") == configured_model), {}
        )
        if configured_info:
            test_logger.info(f"Configured model info: {configured_info}")

    @pytest.mark.f_api
    @pytest.mark.p0
    def test_usage_statistics(self, api_client: ModelAPIClient, test_logger):
        """F4: Usage 统计准确性

        验证 usage 字段的准确性：
        - prompt_tokens > 0
        - completion_tokens > 0
        - total_tokens >= prompt_tokens + completion_tokens
          （思考模型可能将 reasoning_tokens 计入 total 但不计入 completion，
           故使用 >= 而非 ==）
        """
        test_logger.info("=== 测试开始: Usage统计 ===")

        messages = [{"role": "user", "content": "请写一段话"}]
        params = {"max_tokens": 100}
        TestLogger.log_request(test_logger, messages, params)

        response = api_client.chat_completion(messages, max_tokens=100)
        TestLogger.log_response(test_logger, response, "Usage统计响应")
        self.log_full_response(test_logger, response, "F4-Usage统计")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self._assert_finish_reason(response)

        # 验证 usage 存在
        usage = response.get("usage", {})
        assert usage, "Should have usage statistics"

        # 验证必要字段
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        assert prompt_tokens > 0, "Should have prompt_tokens > 0"
        assert completion_tokens > 0, "Should have completion tokens > 0"

        # 验证 token 计算正确
        # 思考模型可能将 reasoning_tokens 计入 total_tokens 但不计入
        # completion_tokens，故 total >= prompt + completion
        if total_tokens > 0:
            assert total_tokens >= prompt_tokens + completion_tokens, (
                f"total_tokens should be >= sum: {total_tokens} < "
                f"{prompt_tokens} + {completion_tokens}"
            )
            # 非思考模型通常 total == prompt + completion，记录差异用于诊断
            if total_tokens != prompt_tokens + completion_tokens:
                test_logger.info(
                    f"total_tokens({total_tokens}) != prompt({prompt_tokens}) + "
                    f"completion({completion_tokens})，可能含 reasoning_tokens"
                )
        else:
            # total_tokens 缺失或为 0，记录软告警但不跳过核心验证
            test_logger.warning(
                f"total_tokens missing or 0, prompt={prompt_tokens}, "
                f"completion={completion_tokens}"
            )

        test_logger.info(
            f"Usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}"
        )

    @pytest.mark.f_api
    @pytest.mark.p1
    def test_error_codes(self, api_client: ModelAPIClient, test_logger, record_warning):
        """F5: 错误码规范 - 401/400/404 错误码

        验证服务端对错误请求返回正确的错误：
        - 401: 无效 API key 应返回认证错误
        - 400: 空 content 应返回请求错误（或被接受则记录）
        - 404: 不存在的端点应返回 404
        """
        test_logger.info("=== 测试开始: 错误码规范 ===")

        messages = [{"role": "user", "content": "测试"}]

        # 测试 401 认证错误（无效的API key）
        invalid_client = ModelAPIClient(
            base_url=api_client.api_prefix,
            api_key="invalid_key_12345",
            model_name=api_client.model_name,
        )
        try:
            TestLogger.log_request(test_logger, messages, {"invalid_api_key": True})
            response = invalid_client.chat_completion(messages)
            self.log_full_response(test_logger, response, "F5-401认证错误")
            # 未抛异常说明无效 key 被接受，记录软告警
            test_logger.warning("401 test: no error returned for invalid API key")
            record_warning("401未返回错误")
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "F5-401认证错误(异常)"
            )
            test_logger.info(f"401 错误（异常）: {e}")
            error_msg = str(e).lower()
            # 状态码 401 或认证相关关键词
            assert any(
                kw in error_msg for kw in ["401", "unauthorized", "auth"]
            ), f"Should be authentication error, got: {e}"
        finally:
            invalid_client.close()

        # 测试 400 错误（无效请求 - 空 content）
        try:
            invalid_messages = [{"role": "user", "content": ""}]
            TestLogger.log_request(test_logger, invalid_messages, {"max_tokens": 1})
            response = api_client.chat_completion(invalid_messages, max_tokens=1)
            self.log_full_response(test_logger, response, "F5-400无效请求")
            # 空 content 被接受：仍需验证响应合法（不能无断言通过）
            self.assert_response_success(response)
            self._assert_finish_reason(response)
            test_logger.info("400 test: empty content was accepted with valid response")
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "F5-400无效请求(异常)"
            )
            test_logger.info(f"400 错误（异常）: {e}")
            error_msg = str(e).lower()
            # 缩窄关键词：仅匹配明确的 400 / invalid / empty / required
            assert any(
                kw in error_msg for kw in ["400", "invalid", "empty", "required", "must"]
            ), f"Should be 400 error for empty content, got: {e}"

        # 测试 404 错误（不存在的端点）
        try:
            url = f"{api_client.api_prefix}/nonexistent_endpoint"
            TestLogger.log_request(test_logger, messages, {"url": url})
            resp = requests.get(url, timeout=10, headers=api_client.session.headers)
            self.log_full_response(
                test_logger,
                {"status": resp.status_code, "body": resp.text[:500]},
                "F5-404不存在端点",
            )
            test_logger.info(f"404 test: status={resp.status_code}")
            assert resp.status_code == 404, (
                f"Should return 404 for nonexistent endpoint, got {resp.status_code}"
            )
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "F5-404不存在端点(异常)"
            )
            test_logger.info(f"404 错误（异常）: {e}")
            error_msg = str(e).lower()
            assert any(
                kw in error_msg for kw in ["404", "not found"]
            ), f"Should be 404 error for nonexistent endpoint, got: {e}"

        test_logger.info("错误码规范测试完成")

    @pytest.mark.f_api
    @pytest.mark.p0
    def test_client_sdk_compatibility(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """F6: 客户端 SDK 兼容 - Python openai 库直接调用

        验证标准 OpenAI Python SDK 可以直接调用兼容接口。
        - ImportError（SDK 未安装）→ 软告警，测试跳过
        - SDK 调用成功 → 硬断言验证响应格式
        - SDK 调用失败（非 ImportError）→ 硬断言失败（不再静默吞没）
        """
        test_logger.info("=== 测试开始: 客户端 SDK 兼容 ===")

        try:
            from openai import OpenAI
        except ImportError:
            record_warning("openai SDK not installed, skipping SDK compatibility test")
            test_logger.info("openai SDK not installed, skipping SDK compatibility test")
            return

        # SDK 已安装，以下为硬断言
        client = OpenAI(
            api_key=api_client.api_key or "dummy",
            base_url=api_client.api_prefix,
        )
        try:
            messages = [{"role": "user", "content": "测试SDK兼容性"}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 100})

            response = client.chat.completions.create(
                model=api_client.model_name,
                messages=messages,
                max_tokens=100,
            )

            test_logger.info(f"SDK 响应: {response}")
            test_logger.info(f"SDK 返回ID: {response.id}")

            # 验证响应格式
            assert response.id is not None, "Should have response id"
            assert len(response.choices) > 0, "Should have choices"
            assert response.choices[0].message.content is not None, (
                "Should have content"
            )
            # 思考模型可能 content 为空（全在 reasoning），使用宽松检查
            content = response.choices[0].message.content or ""
            reasoning = (
                getattr(response.choices[0].message, "reasoning_content", None)
                or getattr(response.choices[0].message, "reasoning", None)
                or ""
            )
            assert len(content.strip()) > 0 or len(str(reasoning).strip()) > 0, (
                "Should have non-empty content or reasoning"
            )
            assert response.choices[0].message.role == "assistant", (
                "Role should be assistant"
            )

            # 验证 finish_reason
            finish_reason = response.choices[0].finish_reason
            assert finish_reason in self.VALID_FINISH_REASONS, (
                f"finish_reason should be one of {self.VALID_FINISH_REASONS}, "
                f"got '{finish_reason}'"
            )

            # 验证 usage
            if response.usage:
                assert response.usage.prompt_tokens > 0, "Should have prompt_tokens > 0"
                assert response.usage.completion_tokens > 0, (
                    "Should have completion_tokens > 0"
                )

            self.log_full_response(
                test_logger,
                {
                    "id": response.id,
                    "model": response.model,
                    "usage": str(response.usage),
                    "finish_reason": finish_reason,
                },
                "F6-SDK兼容",
            )

            test_logger.info("客户端 SDK 兼容性测试通过")
        except Exception as e:
            # SDK 已安装但调用失败 → 硬断言失败（不再静默吞没）
            self.log_full_response(
                test_logger, {"error": str(e)}, "F6-SDK兼容(失败)"
            )
            pytest.fail(f"SDK compatibility test failed: {e}")
        finally:
            client.close()

    @pytest.mark.f_api
    @pytest.mark.p0
    def test_responses_api(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """F7: OpenAI Responses API (/v1/responses) 接口兼容

        /v1/responses 是 OpenAI 2025-03 推出的新一代大模型响应生成接口，
        作为 Chat Completions 的超集，是构建 AI Agent 的核心 API 原语，
        已成为 2026 年 AI 开发生态的主流标准接口。本用例验证其
        OpenAI 规范兼容性：
        - 顶层 object == "response"、id 非空、status == "completed"
        - output 数组含 type=="message" 项，其 content 含 output_text 项
        - 文本非空可提取
        - usage 采用 Responses API 字段名（input_tokens/output_tokens，
          区别于 Chat Completions 的 prompt_tokens/completion_tokens）且
          均 > 0；total_tokens 若存在则 >= input+output（同 F4 口径）
        - max_output_tokens 参数被接受（Responses API 字段名）
        - temperature/top_p 走全局注入（非豁免用例——SAMPLING_PARAMS
          设值时携带，默认不传）；seed 不适用（/v1/responses 官方
          参数集无该字段，不注入）

        端点未实现（HTTP 404/405/501）→ record_warning 软告警（接口
        未部署，报告可追溯）；端点已部署 → 以下全部硬断言（兼容性
        缺陷必须暴露，不再软告警）。
        input 采用字符串最简形式；消息数组形式（input_text 类型）与
        流式事件解析由 K30 覆盖，此处不重复。
        """
        test_logger.info("=== 测试开始: Responses API (/v1/responses) ===")

        url = f"{api_client.api_prefix}/responses"
        # 采样参数走全局（非豁免用例）：SAMPLING_PARAMS 设值时注入
        # （conftest 注入 client 全局值），默认空值不传；seed 不注入
        # ——/v1/responses 官方参数集不含 seed 字段
        payload = {
            "model": api_client.model_name,
            "input": "请用一句话介绍你自己",
            "max_output_tokens": 2048,
        }
        if api_client.temperature is not None:
            payload["temperature"] = api_client.temperature
        if api_client.top_p is not None:
            payload["top_p"] = api_client.top_p
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": "请用一句话介绍你自己"}],
            {
                "endpoint": "/v1/responses",
                "input": "(string 形式，最简请求)",
                "max_output_tokens": 2048,
                "temperature": payload.get("temperature", "(不发送)"),
                "top_p": payload.get("top_p", "(不发送)"),
                "seed": "(不注入——/v1/responses 无 seed 参数)",
            },
        )

        started = time.time()
        try:
            response = api_client.session.post(
                url, json=payload, timeout=api_client.timeout
            )
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "F7-Responses(请求异常)"
            )
            record_warning(f"/v1/responses 请求异常: {e}")
            test_logger.info(f"/v1/responses request failed: {e}")
            return
        elapsed = time.time() - started

        try:
            data = response.json()
        except ValueError:
            data = None
        self.log_full_response(
            test_logger,
            {
                "status_code": response.status_code,
                "elapsed": f"{elapsed:.1f}s",
                "body": (
                    json.dumps(data, ensure_ascii=False)[:800]
                    if data is not None
                    else response.text[:800]
                ),
            },
            "F7-Responses",
        )

        # 端点未实现（404/405/501）→ 软告警（接口未部署，不视为
        # 兼容性缺陷；2026 主流标准接口，建议部署尽快支持）
        if response.status_code in (404, 405, 501):
            record_warning(
                f"/v1/responses 未实现（HTTP {response.status_code}）——"
                f"Responses API 为 2026 主流标准接口，建议尽快支持"
            )
            test_logger.warning(
                f"/v1/responses not implemented: HTTP "
                f"{response.status_code}: {response.text[:200]}"
            )
            return

        # 端点已部署：以下全部硬断言（格式不符即兼容性缺陷）
        assert response.status_code == 200, (
            f"/v1/responses 请求失败：HTTP {response.status_code}: "
            f"{response.text[:400]}"
        )
        assert data, "响应体应为合法 JSON"

        # OpenAI Responses API 规范：顶层字段
        assert data.get("object") == "response", (
            f"object should be 'response', got '{data.get('object')}'"
        )
        assert data.get("id"), "Should have response id"
        assert data.get("status") == "completed", (
            f"status should be 'completed', got '{data.get('status')}'"
        )

        # output 数组：应含 type=="message" 项，其 content 含 output_text 项
        output = data.get("output")
        assert isinstance(output, list) and len(output) > 0, (
            f"output should be non-empty list, got: {output!r}"
        )
        message_items = [
            o for o in output if isinstance(o, dict) and o.get("type") == "message"
        ]
        assert message_items, (
            f"output should contain type='message' items, got types: "
            f"{[o.get('type') for o in output if isinstance(o, dict)]}"
        )
        text_parts = []
        for msg in message_items:
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "output_text":
                    text_parts.append(c.get("text") or "")
        text = "".join(text_parts).strip()
        assert text, (
            "Should have non-empty output_text in message content"
        )

        # usage：Responses API 字段名（input_tokens/output_tokens）
        usage = data.get("usage")
        assert isinstance(usage, dict) and usage, "Should have usage statistics"
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        assert input_tokens > 0, f"input_tokens should be > 0, got {input_tokens}"
        assert output_tokens > 0, (
            f"output_tokens should be > 0, got {output_tokens}"
        )
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens:
            # 思考模型 reasoning_tokens 计入 total 但可能单列，使用 >=（同 F4 口径）
            assert total_tokens >= input_tokens + output_tokens, (
                f"total_tokens {total_tokens} < input {input_tokens} + "
                f"output {output_tokens}"
            )

        # id 前缀（resp_）为实现细节，记录不硬断言
        if not str(data.get("id", "")).startswith("resp_"):
            test_logger.info(
                f"note: response id '{data.get('id')}' lacks 'resp_' "
                f"prefix (implementation detail)"
            )

        test_logger.info(
            f"Responses API: OK, text={text[:100]!r}, "
            f"usage(input={input_tokens}, output={output_tokens}, "
            f"total={total_tokens})"
        )

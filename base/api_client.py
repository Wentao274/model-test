"""
模型API客户端封装
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional, Iterator, Union
import requests

try:
    import allure
    from allure_commons.types import AttachmentType

    ALLURE_AVAILABLE = True
except ImportError:
    ALLURE_AVAILABLE = False


logger = logging.getLogger(__name__)

# 需要重试的瞬时网络异常。
# 仅含 ConnectionError：覆盖连接被对端重置 (ConnectionResetError) 以及
# 连接建立超时 (ConnectTimeout，它是 ConnectionError 的子类)。
# 不含 ReadTimeout —— 超长上下文 prefill 等场景的读取超时往往意味着模型
# 无法在合理时间内处理该规模输入，重试只会白白浪费数倍 timeout 时间，
# 应由调用方的 _is_over_limit_error / skip 逻辑处理。
_RETRYABLE_EXCEPTIONS = (requests.exceptions.ConnectionError,)


def _attach_api_error(status_code: int, response_text: str, payload: dict):
    """将非200响应的状态码与响应体作为附件挂到 Allure，便于在报告中直接查看"""
    if not ALLURE_AVAILABLE:
        return
    try:
        content = (
            f"HTTP Status: {status_code}\n\n"
            f"Response Body:\n{response_text}\n\n"
            f"Request Payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        allure.attach(
            content,
            name=f"API Error: {status_code}",
            attachment_type=AttachmentType.TEXT,
        )
    except Exception:
        pass


class ModelAPIClient:
    """模型API客户端，封装OpenAI兼容的API调用"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout: int = 120,
        config: Dict[str, Any] = None,
        reasoning_effort: Optional[str] = None,
        seed: Optional[str] = None,
        retry_times: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.model_name = model_name
        self.timeout = timeout
        self.config = config or {}
        self.retry_times = max(0, int(retry_times))
        # 全局 reasoning_effort / seed：非空时自动注入到每次 chat_completion 请求；
        # 调用方显式传入的同名参数优先级更高（不会被子覆盖）。
        self.reasoning_effort = reasoning_effort.strip() if reasoning_effort else None
        self.seed = seed.strip() if seed else None
        self.session = requests.Session()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.session.headers.update(headers)

    def _inject_global_params(self, kwargs: Dict[str, Any]) -> None:
        """将全局 reasoning_effort / seed 注入到请求 kwargs 中（原地修改）

        仅当全局值非空、且调用方未显式指定该参数时注入。显式参数可能位于：
        - kwargs 顶层（如 seed=42）
        - kwargs["extra_body"]（如 {"reasoning_effort": "low"}）

        因此同时检查两层，避免与调用方显式值冲突。
        """
        if self.reasoning_effort:
            extra_body = kwargs.get("extra_body") or {}
            if "reasoning_effort" not in kwargs and "reasoning_effort" not in extra_body:
                kwargs["reasoning_effort"] = self.reasoning_effort
        if self.seed:
            extra_body = kwargs.get("extra_body") or {}
            if "seed" not in kwargs and "seed" not in extra_body:
                try:
                    kwargs["seed"] = int(self.seed)
                except (ValueError, TypeError):
                    kwargs["seed"] = self.seed

    def get_thinking_params(self, enabled: bool = None) -> Dict[str, Any]:
        """根据模型配置生成思考模式参数

        Args:
            enabled: 是否启用思考模式，默认使用模型的 thinking_mode 配置
        """
        if enabled is None:
            enabled = self.config.get("thinking_mode", False)

        if not enabled:
            return {}

        use_chat_template = self.config.get("thinking_via_chat_template", False)
        thinking_key = self.config.get("thinking_key", "enable_thinking")

        if use_chat_template:
            return {"chat_template_kwargs": {thinking_key: enabled}}
        else:
            return {thinking_key: enabled}

    def _post_with_retry(
        self, url: str, payload: dict, stream: bool = False
    ) -> requests.Response:
        """发送 POST 请求，遇到瞬时网络错误（如连接被对端重置）时自动重试。

        Args:
            url: 请求地址
            payload: 请求体
            stream: 是否流式

        Returns:
            requests.Response 对象
        """
        last_exc = None
        attempts = self.retry_times + 1
        for attempt in range(1, attempts + 1):
            try:
                return self.session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                    stream=stream,
                )
            except _RETRYABLE_EXCEPTIONS as e:
                last_exc = e
                if attempt >= attempts:
                    logger.error(
                        "API request to %s failed after %d attempts: %s",
                        url,
                        attempts,
                        e,
                    )
                    raise
                # 丢弃可能已失效的连接，避免复用被对端关闭的 keep-alive 连接
                try:
                    self.session.close()
                except Exception:
                    pass
                backoff = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "API request to %s failed (attempt %d/%d): %s. "
                    "Retrying in %ds...",
                    url,
                    attempt,
                    attempts,
                    e,
                    backoff,
                )
                time.sleep(backoff)
        # 逻辑上不可达，保险起见
        raise last_exc  # type: ignore[misc]

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs,
    ) -> Union[Dict[str, Any], Iterator[Dict[str, Any]]]:
        """
        发送聊天完成请求

        Args:
            messages: 消息列表
            model: 模型名称（默认使用实例配置）
            temperature: 温度参数
            max_tokens: 最大生成token数
            stream: 是否流式输出
            **kwargs: 其他API参数

        Returns:
            非流式: 完整响应字典
            流式: SSE事件迭代器
        """
        self._inject_global_params(kwargs)
        if stream:
            return self.chat_completion_stream(
                messages, model, temperature, max_tokens, **kwargs
            )

        extra_body = kwargs.pop("extra_body", None)

        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **kwargs,
        }
        if extra_body:
            payload.update(extra_body)

        response = self._post_with_retry(url, payload, stream=False)

        # 检查响应状态
        if response.status_code != 200:
            _attach_api_error(response.status_code, response.text, payload)
            raise Exception(
                f"API request failed with status {response.status_code}: {response.text}"
            )

        # 检查响应内容
        if not response.text or response.text.strip() == "":
            raise Exception(
                f"API returned empty response. Status: {response.status_code}"
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise Exception(
                f"Failed to parse JSON response: {e}. Response text: {response.text[:500]}"
            )

    def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> Iterator[Dict[str, Any]]:
        """发送聊天完成请求（流式）"""
        self._inject_global_params(kwargs)
        extra_body = kwargs.pop("extra_body", None)

        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if extra_body:
            payload.update(extra_body)

        response = self._post_with_retry(url, payload, stream=True)

        # 检查响应状态
        if response.status_code != 200:
            _attach_api_error(response.status_code, response.text, payload)
            raise Exception(
                f"API request failed with status {response.status_code}: {response.text[:500]}"
            )

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield json.loads(data)

    def list_models(self) -> Dict[str, Any]:
        """获取模型列表"""
        url = f"{self.base_url}/v1/models"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def completion(
        self, prompt: str, model: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """传统Completion API"""
        url = f"{self.base_url}/v1/completions"
        payload = {"model": model or self.model_name, "prompt": prompt, **kwargs}
        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息"""
        models = self.list_models()
        for model in models.get("data", []):
            if model.get("id") == self.model_name:
                return model
        return {}

    def close(self):
        """关闭会话"""
        self.session.close()


class StreamingMetrics:
    """流式响应指标计算"""

    def __init__(self):
        self.start_time: float = 0
        self.token_times: List[float] = []
        self.tokens: List[str] = []
        self.first_token_received: bool = False

    def start(self):
        """开始计时"""
        self.start_time = time.time()

    def record_token(self, token: str, timestamp: Optional[float] = None):
        """记录token"""
        if timestamp is None:
            timestamp = time.time()

        if not self.first_token_received:
            self.first_token_received = True
            self.first_token_time = timestamp

        self.token_times.append(timestamp)
        self.tokens.append(token)

    @property
    def ttft(self) -> float:
        """首Token时间 (Time to First Token)"""
        if not self.first_token_received:
            return 0
        return self.first_token_time - self.start_time

    @property
    def tpot(self) -> float:
        """平均每Token生成时间 (Time Per Output Token)"""
        if len(self.token_times) < 2:
            return 0
        total_time = sum(
            self.token_times[i] - self.token_times[i - 1]
            for i in range(1, len(self.token_times))
        )
        return total_time / (len(self.token_times) - 1)

    @property
    def total_time(self) -> float:
        """总时间"""
        if self.token_times:
            return self.token_times[-1] - self.start_time
        return 0

    @property
    def token_count(self) -> int:
        """Token数量"""
        return len(self.tokens)

    @property
    def throughput(self) -> float:
        """吞吐量 (tokens/s)"""
        if self.total_time > 0:
            return self.token_count / self.total_time
        return 0

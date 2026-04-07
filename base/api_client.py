"""
模型API客户端封装
"""
import json
import time
from typing import Dict, Any, List, Optional, Iterator, Union
import requests


class ModelAPIClient:
    """模型API客户端，封装OpenAI兼容的API调用"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout: int = 120
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs
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
        if stream:
            return self.chat_completion_stream(messages, model, temperature, max_tokens, **kwargs)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **kwargs
        }

        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> Iterator[Dict[str, Any]]:
        """发送聊天完成请求（流式）"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs
        }

        response = self.session.post(url, json=payload, timeout=self.timeout, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    yield json.loads(data)

    def list_models(self) -> Dict[str, Any]:
        """获取模型列表"""
        url = f"{self.base_url}/models"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """传统Completion API"""
        url = f"{self.base_url}/completions"
        payload = {
            "model": model or self.model_name,
            "prompt": prompt,
            **kwargs
        }
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
            self.token_times[i] - self.token_times[i-1]
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
"""
E. 性能指标测试

测试点：
- E1: TTFT（首Token延迟）
- E2: TPOT（每Token生成时间）
- E3: ITL P50/P95/P99
- E4: 端到端延迟
- E5: 吞吐量（tokens/s）
- E6: 请求吞吐（req/s）
- E7: 并发扩展性
- E8: 显存占用
- E9: GPU利用率
- E10: 预热时间
- E11: Prefill速度
- E12: 突发流量恢复
"""
import pytest
import time
import statistics
import concurrent.futures
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient, StreamingMetrics


class TestPerformance(BaseTest):
    """性能指标测试类"""

    def get_test_category(self) -> str:
        return "E. 性能指标"

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_ttft(self, api_client: ModelAPIClient):
        """E1: TTFT（首Token延迟）"""
        messages = [{"role": "user", "content": "请给我讲一个长故事"}]

        # 预热
        api_client.chat_completion(messages[:1], max_tokens=10)

        # 正式测试
        start = time.time()
        response_iter = api_client.chat_completion_stream(messages, max_tokens=100)

        ttft = None
        for chunk in response_iter:
            if chunk.get("choices") and chunk["choices"][0].get("delta"):
                delta = chunk["choices"][0]["delta"]
                if delta.get("content") or delta.get("reasoning_content"):
                    ttft = time.time() - start
                    break

        assert ttft is not None, "Should receive first token"
        print(f"TTFT: {ttft*1000:.2f}ms")

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_tpot(self, api_client: ModelAPIClient):
        """E2: TPOT（每Token生成时间）"""
        messages = [{"role": "user", "content": "请写一首诗"}]

        response_iter = api_client.chat_completion_stream(messages, max_tokens=50)

        metrics = StreamingMetrics()
        metrics.start()

        token_count = 0
        last_time = time.time()

        for chunk in response_iter:
            if chunk.get("choices") and chunk["choices"][0].get("delta"):
                delta = chunk["choices"][0]["delta"]
                if delta.get("content"):
                    current_time = time.time()
                    metrics.record_token(delta["content"], current_time)
                    token_count += 1
                    if token_count >= 20:
                        break

        tpot = metrics.tpot
        print(f"TPOT: {tpot*1000:.2f}ms, Token count: {token_count}")
        assert token_count > 0, "Should receive tokens"

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_itl_percentiles(self, api_client: ModelAPIClient):
        """E3: ITL P50/P95/P99"""
        messages = [{"role": "user", "content": "请回答：1+1=?"}]

        # 多次测试
        latencies = []
        for _ in range(10):
            start = time.time()
            response_iter = api_client.chat_completion_stream(messages, max_tokens=30)
            for chunk in response_iter:
                if chunk.get("choices") and chunk["choices"][0].get("delta"):
                    delta = chunk["choices"][0]["delta"]
                    if delta.get("content"):
                        latencies.append(time.time() - start)
                        break

        if latencies:
            p50 = statistics.median(latencies)
            p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
            p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
            print(f"ITL P50: {p50*1000:.2f}ms, P95: {p95*1000:.2f}ms, P99: {p99*1000:.2f}ms")

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_end_to_end_latency(self, api_client: ModelAPIClient):
        """E4: 端到端延迟"""
        messages = [{"role": "user", "content": "请回答：什么是人工智能？"}]

        start = time.time()
        response = api_client.chat_completion(messages, max_tokens=100)
        latency = time.time() - start

        self.assert_response_success(response)
        print(f"End-to-end latency: {latency*1000:.2f}ms")

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_token_throughput(self, api_client: ModelAPIClient):
        """E5: 吞吐量（tokens/s）"""
        messages = [{"role": "user", "content": "请写一首诗，越长越好"}]

        start = time.time()
        response_iter = api_client.chat_completion_stream(messages, max_tokens=100)

        token_count = 0
        for chunk in response_iter:
            if chunk.get("choices") and chunk["choices"][0].get("delta"):
                delta = chunk["choices"][0]["delta"]
                if delta.get("content"):
                    token_count += 1

        duration = time.time() - start
        throughput = token_count / duration if duration > 0 else 0

        print(f"Token throughput: {throughput:.2f} tokens/s, Duration: {duration:.2f}s")

    @pytest.mark.e_performance
    @pytest.mark.p0
    def test_request_throughput(self, api_client: ModelAPIClient):
        """E6: 请求吞吐（req/s）"""
        messages = [{"role": "user", "content": "你好"}]

        start = time.time()
        count = 0
        for _ in range(5):
            response = api_client.chat_completion(messages, max_tokens=20)
            if response.get("choices"):
                count += 1

        duration = time.time() - start
        throughput = count / duration if duration > 0 else 0

        print(f"Request throughput: {throughput:.2f} req/s")

    @pytest.mark.e_performance
    @pytest.mark.p0
    @pytest.mark.slow
    def test_concurrency_scaling(self, api_client: ModelAPIClient):
        """E7: 并发扩展性"""
        # 简单并发测试
        messages = [{"role": "user", "content": "请回答一个简单问题"}]

        def make_request():
            start = time.time()
            response = api_client.chat_completion(messages, max_tokens=50)
            return time.time() - start, response.get("choices") is not None

        # 10并发
        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]

        duration = time.time() - start
        success_count = sum(1 for _, success in results if success)

        print(f"10 concurrent requests: {success_count}/10 success, Duration: {duration:.2f}s")
        assert success_count >= 8, "Should handle concurrent requests"

    @pytest.mark.e_performance
    @pytest.mark.p0
    @pytest.mark.skip(reason="需要nvidia-smi工具")
    def test_gpu_memory(self, api_client: ModelAPIClient):
        """E8: 显存占用"""
        pytest.skip("Requires nvidia-smi")

    @pytest.mark.e_performance
    @pytest.mark.p1
    @pytest.mark.skip(reason="需要nvidia-smi工具")
    def test_gpu_utilization(self, api_client: ModelAPIClient):
        """E9: GPU利用率"""
        pytest.skip("Requires nvidia-smi")

    @pytest.mark.e_performance
    @pytest.mark.p1
    def test_warmup_time(self, api_client: ModelAPIClient):
        """E10: 预热时间 - 首次推理vs稳态推理"""
        messages = [{"role": "user", "content": "测试"}]

        # 首次请求
        start = time.time()
        api_client.chat_completion(messages, max_tokens=10)
        first_latency = time.time() - start

        # 预热后请求
        start = time.time()
        api_client.chat_completion(messages, max_tokens=10)
        warm_latency = time.time() - start

        print(f"First request: {first_latency*1000:.2f}ms, Warm request: {warm_latency*1000:.2f}ms")

    @pytest.mark.e_performance
    @pytest.mark.p1
    @pytest.mark.slow
    def test_prefill_speed(self, api_client: ModelAPIClient):
        """E11: Prefill速度"""
        test_cases = [
            ("短文本", "测试" * 50),
            ("中文本", "测试" * 500),
            ("长文本", "测试" * 2000),
        ]

        for name, prompt in test_cases:
            messages = [{"role": "user", "content": prompt}]
            start = time.time()
            response = api_client.chat_completion(messages, max_tokens=10)
            latency = time.time() - start
            print(f"Prefill ({name}): {latency*1000:.2f}ms")

    @pytest.mark.e_performance
    @pytest.mark.p1
    @pytest.mark.slow
    def test_burst_recovery(self, api_client: ModelAPIClient):
        """E12: 突发流量恢复"""
        messages = [{"role": "user", "content": "测试突发流量"}]

        # 突发请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(api_client.chat_completion, messages, 20) for _ in range(20)]
            results = [f.result() for f in futures]

        # 等待恢复
        time.sleep(2)

        # 正常请求
        start = time.time()
        response = api_client.chat_completion(messages, max_tokens=50)
        recovery_latency = time.time() - start

        print(f"Recovery latency: {recovery_latency*1000:.2f}ms")
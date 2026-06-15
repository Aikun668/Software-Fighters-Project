#!/usr/bin/env python3
"""
Knowledge Graph API 多维度压力测试脚本.

Usage:
  # 先启动服务（另一个终端）:
  USE_MOCK_LLM=true python main.py

  # 然后运行压力测试:
  python tests/stress_test_knowledge_graph.py

  python tests/stress_test_knowledge_graph.py --url http://127.0.0.1:8001 --concurrency 50 --duration 10
"""

import asyncio
import json
import random
import statistics
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Optional

import httpx

# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

BASE_URL = "http://127.0.0.1:8001"
GRAPH_EXTRACT_URL = f"{BASE_URL}/internal/graph/extract"
GRAPH_NODES_URL = f"{BASE_URL}/internal/graph/nodes"
HEALTH_URL = f"{BASE_URL}/health"

DEFAULT_CONCURRENCY = 20
DEFAULT_DURATION = 10           # seconds per phase
DEFAULT_BURST_DURATION = 5
DEFAULT_BURST_CONCURRENCY = 100

# Realistic payloads — mix of Chinese, English, long, short, edge cases
EXTRACT_PAYLOADS: list[dict] = [
    # 中文短对话
    {
        "course_id": "ai_intro",
        "user_message": "什么是反向传播算法？",
        "assistant_reply": "反向传播（Backpropagation）是训练神经网络的核心算法。它通过链式法则从输出层向输入层逐层计算梯度，然后使用梯度下降更新权重。关键步骤包括：前向传播计算预测值、计算损失函数、反向传播计算梯度、更新参数。",
        "existing_node_ids": ["neural_network", "gradient_descent"],
    },
    # 英文短对话
    {
        "course_id": "ai_intro",
        "user_message": "Explain CNN architecture",
        "assistant_reply": "CNN consists of convolutional layers for feature extraction, pooling layers for downsampling, and fully connected layers for classification. Key concepts include kernels, stride, padding, and activation maps.",
        "existing_node_ids": ["dl_basics"],
    },
    # 中文多知识点
    {
        "course_id": "ai_intro",
        "user_message": "Transformer和RNN有什么区别？",
        "assistant_reply": "Transformer和RNN是两种不同的序列建模架构。RNN按时间步递归处理，存在梯度消失和无法并行的问题。Transformer使用自注意力机制，可以并行计算所有位置的关系，通过位置编码保留序列信息。Transformer的核心组件包括多头注意力、前馈网络、层归一化和残差连接。",
        "existing_node_ids": ["transformer", "rnn"],
    },
    # 长文本
    {
        "course_id": "ai_intro",
        "user_message": "详细讲解一下强化学习的基本概念和应用场景",
        "assistant_reply": "强化学习（Reinforcement Learning）是机器学习的三大范式之一。" * 50,
        "existing_node_ids": [],
    },
    # 含代码示例
    {
        "course_id": "ai_intro",
        "user_message": "怎么写一个PyTorch训练循环？",
        "assistant_reply": "PyTorch训练循环的标准写法如下：首先定义模型model = nn.Module，然后定义损失函数criterion = nn.CrossEntropyLoss()和优化器optimizer = torch.optim.Adam(model.parameters())。训练循环中：for epoch in range(epochs): 前向传播 outputs = model(inputs)，计算损失 loss = criterion(outputs, labels)，反向传播 loss.backward()，参数更新 optimizer.step()，清零梯度 optimizer.zero_grad()。",
        "existing_node_ids": ["python_basics", "dl_basics"],
    },
    # 空白已存在ID
    {
        "course_id": "ai_intro",
        "user_message": "激活函数有哪些选择？",
        "assistant_reply": "常见的激活函数包括ReLU（最常用，计算简单）、Sigmoid（输出0-1，用于二分类）、Tanh（输出-1到1）、LeakyReLU（解决ReLU死亡神经元问题）、ELU、GELU（Transformer中使用）。选择建议：隐藏层优先ReLU及其变体，输出层根据任务选择（分类用Softmax/Sigmoid，回归用线性）。",
        "existing_node_ids": [],
    },
]

NODE_ADD_PAYLOADS: list[dict] = []


def _make_node_payloads(count: int = 20) -> list[dict]:
    """Generate unique node-add payloads, each with a unique id based on timestamp+index."""
    import time as _time
    ts = int(_time.time() * 1000)
    return [
        {
            "course_id": "ai_intro",
            "updates": [{"action": "add_node", "data": {
                "id": f"stress_{ts}_{j:04d}",
                "name": f"stress-node-{ts}-{j}",
                "type": "concept",
                "difficulty": (j % 5) + 1,
            }}],
        }
        for j in range(count)
    ]


def _next_node_payload() -> dict:
    """Generate a fresh, guaranteed-unique node-add payload."""
    import time as _time
    ts = int(_time.time() * 1_000_000)
    rid = random.randint(0, 99999)
    return {
        "course_id": "ai_intro",
        "updates": [{"action": "add_node", "data": {
            "id": f"stress_{ts}_{rid:05d}",
            "name": f"stress-node-{ts}-{rid}",
            "type": "concept",
            "difficulty": random.randint(1, 5),
        }}],
    }


# ═══════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Metrics:
    latencies: list[float] = field(default_factory=list)
    errors: int = 0
    success: int = 0
    status_codes: dict[int, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.success + self.errors

    def summary(self, label: str = "") -> str:
        if not self.latencies:
            return f"[{label}] 0 requests"
        sorted_lat = sorted(self.latencies)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        avg = statistics.mean(self.latencies)
        tput = self.total / (sorted_lat[-1] - sorted_lat[0]) if len(sorted_lat) > 1 else 0
        lines = [
            f"\n{'='*60}",
            f"  {label}",
            f"{'='*60}",
            f"  Total:      {self.total}  (ok={self.success}  err={self.errors})",
            f"  Throughput: {tput:.1f} req/s",
            f"  Latency:    avg={avg*1000:.1f}ms  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  p99={p99*1000:.1f}ms",
            f"  Statuses:   {dict(self.status_codes)}",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# HTTP client workers
# ═══════════════════════════════════════════════════════════════════


async def _send_one(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    metrics: Metrics,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, json=payload, timeout=httpx.Timeout(60))
            elapsed = time.perf_counter() - t0
            metrics.latencies.append(elapsed)
            code = resp.status_code
            metrics.status_codes[code] = metrics.status_codes.get(code, 0) + 1
            if 200 <= code < 300:
                metrics.success += 1
            else:
                metrics.errors += 1
        except Exception:
            metrics.errors += 1
            metrics.latencies.append(time.perf_counter() - t0)


async def _bombard_phase(
    client: httpx.AsyncClient,
    url: str,
    payloads: list[dict],
    concurrency: int,
    duration: float,
    label: str,
    dynamic_payload: Optional[Callable] = None,
) -> Metrics:
    sem = asyncio.Semaphore(concurrency)
    metrics = Metrics()
    deadline = time.monotonic() + duration

    async def worker():
        while time.monotonic() < deadline:
            payload = dynamic_payload() if dynamic_payload else random.choice(payloads)
            async with sem:
                t0 = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload, timeout=httpx.Timeout(60))
                    elapsed = time.perf_counter() - t0
                    metrics.latencies.append(elapsed)
                    code = resp.status_code
                    metrics.status_codes[code] = metrics.status_codes.get(code, 0) + 1
                    if 200 <= code < 300:
                        metrics.success += 1
                    else:
                        metrics.errors += 1
                except Exception:
                    metrics.errors += 1
                    metrics.latencies.append(time.perf_counter() - t0)

    tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.sleep(duration)
    # Let in-flight requests finish
    await asyncio.gather(*tasks, return_exceptions=True)
    print(metrics.summary(label), flush=True)
    return metrics


async def _burst_phase(
    client: httpx.AsyncClient,
    url: str,
    payloads: list[dict],
    concurrency: int,
    label: str,
    dynamic_payload: Optional[Callable] = None,
) -> Metrics:
    """Fire `concurrency` requests simultaneously, wait for all to finish."""
    metrics = Metrics()
    sem = asyncio.Semaphore(concurrency)

    async def one_shot():
        payload = dynamic_payload() if dynamic_payload else random.choice(payloads)
        async with sem:
            t0 = time.perf_counter()
            try:
                resp = await client.post(url, json=payload, timeout=httpx.Timeout(60))
                elapsed = time.perf_counter() - t0
                metrics.latencies.append(elapsed)
                code = resp.status_code
                metrics.status_codes[code] = metrics.status_codes.get(code, 0) + 1
                if 200 <= code < 300:
                    metrics.success += 1
                else:
                    metrics.errors += 1
            except Exception:
                metrics.errors += 1
                metrics.latencies.append(time.perf_counter() - t0)

    tasks = [asyncio.create_task(one_shot()) for _ in range(concurrency)]
    await asyncio.gather(*tasks, return_exceptions=True)
    print(metrics.summary(label), flush=True)
    return metrics


# ═══════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════


async def health_check(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(HEALTH_URL, timeout=httpx.Timeout(5))
        if r.status_code == 200:
            print(f"  Server OK: {r.json()}", flush=True)
            return True
    except Exception as e:
        print(f"  Server unreachable: {e}", flush=True)
    return False


# ═══════════════════════════════════════════════════════════════════
# Sample response validator
# ═══════════════════════════════════════════════════════════════════


async def validate_extract_response(client: httpx.AsyncClient):
    """Send one extract request and validate response structure."""
    payload = EXTRACT_PAYLOADS[0]
    try:
        r = await client.post(GRAPH_EXTRACT_URL, json=payload, timeout=httpx.Timeout(30))
        body = r.json()
        ok = body.get("success", False)
        candidates = body.get("data", {}).get("candidates", [])
        print(f"  Extract validation: success={ok}, candidates={len(candidates)}", flush=True)
        if candidates:
            node = candidates[0]
            expected_keys = {"id", "name", "type", "description", "category", "difficulty", "confidence"}
            missing = expected_keys - node.keys()
            if missing:
                print(f"  WARN: missing keys in candidate: {missing}", flush=True)
            else:
                print(f"  Sample node: id={node['id']}, name={node['name']}, conf={node['confidence']}", flush=True)
        return ok
    except Exception as e:
        print(f"  Extract validation failed: {e}", flush=True)
        return False


async def validate_nodes_response(client: httpx.AsyncClient):
    """Add one node and verify it appears in get_graph."""
    course_id = "ai_intro"
    test_id = f"_stress_validate_{int(time.time())}"
    payload = {
        "course_id": course_id,
        "updates": [{"action": "add_node", "data": {"id": test_id, "name": "验证节点"}}],
    }
    try:
        r = await client.post(GRAPH_NODES_URL, json=payload, timeout=httpx.Timeout(30))
        body = r.json()
        ok = body.get("success", False)
        nodes = body.get("data", {}).get("nodes", [])
        found = any(n["id"] == test_id for n in nodes)
        print(f"  Nodes validation: success={ok}, node_present={found}, total_nodes={len(nodes)}", flush=True)
        return ok and found
    except Exception as e:
        print(f"  Nodes validation failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


async def main(concurrency: int, duration: int, burst: int, url: str):
    global GRAPH_EXTRACT_URL, GRAPH_NODES_URL, HEALTH_URL, NODE_ADD_PAYLOADS
    GRAPH_EXTRACT_URL = f"{url}/internal/graph/extract"
    GRAPH_NODES_URL = f"{url}/internal/graph/nodes"
    HEALTH_URL = f"{url}/health"
    NODE_ADD_PAYLOADS = _make_node_payloads()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  知识图谱 API 压力测试                                      ║
║  Target: {url:<48} ║
║  Concurrency: {concurrency:<4}  Duration: {duration}s  Burst: {burst}     ║
╚══════════════════════════════════════════════════════════════╝
""", flush=True)

    limits = httpx.Limits(max_keepalive_connections=200, max_connections=200)
    async with httpx.AsyncClient(limits=limits) as client:

        # ── Phase 0: health check ──
        print("── Phase 0: Health Check ──", flush=True)
        if not await health_check(client):
            print("\n  Server not reachable. Start it with:", flush=True)
            print("    USE_MOCK_LLM=true python main.py", flush=True)
            return

        # ── Phase 1: validate responses ──
        print("\n── Phase 1: Response Validation ──", flush=True)
        await validate_nodes_response(client)
        await validate_extract_response(client)

        # ── Phase 2: graph/nodes stress ──
        print(f"\n── Phase 2: /graph/nodes 压力 ({duration}s @ {concurrency}并发) ──", flush=True)
        await _bombard_phase(client, GRAPH_NODES_URL, [],
                             concurrency, duration, "graph/nodes",
                             dynamic_payload=_next_node_payload)

        # ── Phase 3: graph/extract stress ──
        print(f"\n── Phase 3: /graph/extract 压力 ({duration}s @ {concurrency}并发) ──", flush=True)
        await _bombard_phase(client, GRAPH_EXTRACT_URL, EXTRACT_PAYLOADS,
                             concurrency, duration, "graph/extract")

        # ── Phase 4: burst mode ──
        print(f"\n── Phase 4: Burst ({burst}并发 同时发起) ──", flush=True)
        await _burst_phase(client, GRAPH_EXTRACT_URL, EXTRACT_PAYLOADS,
                           burst, f"graph/extract burst x{burst}")
        await _burst_phase(client, GRAPH_NODES_URL, [],
                           burst, f"graph/nodes burst x{burst}",
                           dynamic_payload=_next_node_payload)

        # ── Phase 5: mixed load ──
        print(f"\n── Phase 5: Mixed 混合负载 ({duration}s @ {concurrency}并发) ──", flush=True)
        mixed_metrics = Metrics()
        sem = asyncio.Semaphore(concurrency)
        deadline = time.monotonic() + duration

        async def mixed_worker():
            while time.monotonic() < deadline:
                url_, payload = (
                    (GRAPH_NODES_URL, _next_node_payload()) if random.random() < 0.4
                    else (GRAPH_EXTRACT_URL, random.choice(EXTRACT_PAYLOADS))
                )
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        resp = await client.post(url_, json=payload, timeout=httpx.Timeout(60))
                        elapsed = time.perf_counter() - t0
                        mixed_metrics.latencies.append(elapsed)
                        code = resp.status_code
                        mixed_metrics.status_codes[code] = mixed_metrics.status_codes.get(code, 0) + 1
                        if 200 <= code < 300:
                            mixed_metrics.success += 1
                        else:
                            mixed_metrics.errors += 1
                    except Exception:
                        mixed_metrics.errors += 1
                        mixed_metrics.latencies.append(time.perf_counter() - t0)

        tasks = [asyncio.create_task(mixed_worker()) for _ in range(concurrency)]
        await asyncio.sleep(duration)
        await asyncio.gather(*tasks, return_exceptions=True)
        print(mixed_metrics.summary("Mixed (60% extract + 40% nodes)"), flush=True)

    print(f"\n{'='*60}")
    print("  压力测试完成!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = ArgumentParser(description="知识图谱 API 压力测试")
    parser.add_argument("--url", default=BASE_URL, help="服务地址 (default: http://127.0.0.1:8001)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"并发数 (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help=f"每阶段持续时间秒 (default: {DEFAULT_DURATION})")
    parser.add_argument("--burst", type=int, default=DEFAULT_BURST_CONCURRENCY, help=f"突发并发数 (default: {DEFAULT_BURST_CONCURRENCY})")
    args = parser.parse_args()

    asyncio.run(main(args.concurrency, args.duration, args.burst, args.url))

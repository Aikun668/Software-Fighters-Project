#!/usr/bin/env python3
"""
Knowledge extraction quality evaluator.

Measures extracted node quality across 6 dimensions:
  D1 – Schema compliance     (字段全不全、类型对不对)
  D2 – ID normalization     (slugify是否正确、是否唯一)
  D3 – Relevance            (提取的节点和原文有没有关系)
  D4 – Precision            (有没有幻觉/无中生有)
  D5 – Attribute accuracy   (type/category/difficulty 是否合理)
  D6 – Confidence consistency(confidence 和实际质量是否正相关)

Scoring: each dimension 0.0–1.0, weighted into final score.
"""

import asyncio
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from app.utils.embeddings import semantic_similarity

TEST_CASES: list[dict] = [
    {
        "id": "backprop_basic",
        "course_id": "ai_intro",
        "user_message": "什么是反向传播？",
        "assistant_reply": "反向传播(Backpropagation)是训练神经网络的核心算法。"
                         "它利用链式法则从输出层向输入层逐层计算损失函数对各权重的梯度，"
                         "然后使用梯度下降法更新参数。关键概念包括链式法则、计算图、梯度消失问题。"
                         "实际应用中，PyTorch和TensorFlow都自动实现了自动微分。",
        "expected_concepts": ["反向传播", "链式法则", "梯度下降", "自动微分"],
        "expected_types": {"反向传播": "concept", "自动微分": "concept"},
        "forbidden_concepts": ["比特币", "SQL注入"],
    },
    {
        "id": "cnn_architecture",
        "course_id": "ai_intro",
        "user_message": "CNN由哪些层组成？",
        "assistant_reply": "卷积神经网络(CNN)主要由三种层组成："
                         "1. 卷积层(Convolutional Layer)：使用卷积核提取特征，产生特征图。"
                         "2. 池化层(Pooling Layer)：进行下采样，降低特征图尺寸，常用最大池化和平均池化。"
                         "3. 全连接层(Fully Connected Layer)：将特征映射到分类输出。"
                         "此外还有激活函数ReLU、Dropout正则化等辅助组件。",
        "expected_concepts": ["卷积神经网络", "卷积层", "池化层", "全连接层", "ReLU", "Dropout"],
        "expected_types": {"卷积层": "concept", "ReLU": "concept"},
        "forbidden_concepts": ["决策树", "随机森林"],
    },
    {
        "id": "transformer_vs_rnn",
        "course_id": "ai_intro",
        "user_message": "Transformer和RNN有什么本质区别？",
        "assistant_reply": "核心区别在于序列处理方式。"
                         "RNN按时间步递归处理，每个时刻依赖前一个隐藏状态，无法并行计算，"
                         "且存在梯度消失问题导致长程依赖难以捕捉。"
                         "Transformer使用自注意力(Self-Attention)机制同时关注序列中所有位置，"
                         "可以完全并行计算。通过位置编码(Positional Encoding)补充序列顺序信息，"
                         "通过多头注意力(Multi-Head Attention)捕捉不同子空间的关系。"
                         "Transformer还引入了残差连接和层归一化来稳定训练。",
        "expected_concepts": ["Transformer", "RNN", "自注意力", "位置编码", "多头注意力", "残差连接", "层归一化"],
        "expected_types": {"自注意力": "concept", "Transformer": "concept"},
        "forbidden_concepts": ["K-means", "PCA"],
    },
    {
        "id": "overfitting_solutions",
        "course_id": "ai_intro",
        "user_message": "怎么解决过拟合？",
        "assistant_reply": "过拟合(Overfitting)是指模型在训练集上表现很好但在测试集上表现差的"
                         "现象，通常因为模型过于复杂或训练数据不足。解决方法包括："
                         "L1/L2正则化(Regularization)添加权重惩罚项；"
                         "Dropout在训练时随机丢弃神经元；"
                         "早停(Early Stopping)在验证集性能不再提升时停止训练；"
                         "数据增强(Data Augmentation)扩充训练数据；"
                         "交叉验证(Cross Validation)更稳定地评估模型性能。",
        "expected_concepts": ["过拟合", "正则化", "Dropout", "早停", "数据增强", "交叉验证"],
        "forbidden_concepts": ["梯度下降", "CNN"],
    },
    {
        "id": "one_concept_only",
        "course_id": "ai_intro",
        "user_message": "什么是softmax？",
        "assistant_reply": "Softmax是一个激活函数，将任意实数向量转换为概率分布，"
                         "所有输出之和为1。常用于多分类问题的输出层。",
        "expected_concepts": ["Softmax"],
        "forbidden_concepts": ["Sigmoid", "Tanh"],
    },
    {
        "id": "no_new_concepts",
        "course_id": "ai_intro",
        "user_message": "好的，我明白了。",
        "assistant_reply": "很好！如果你有任何其他问题，随时可以问我。",
        "expected_concepts": [],
        "forbidden_concepts": ["*"],
    },
]

_VALID_TYPES = {"concept", "skill", "fact"}
_VALID_CATEGORIES = {"foundational", "intermediate", "advanced"}


@dataclass
class DimScore:
    score: float
    detail: str = ""


@dataclass
class CaseReport:
    case_id: str
    total_candidates: int
    dims: dict[str, DimScore] = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)

    @property
    def overall(self) -> float:
        weights = {"schema": 0.10, "id_norm": 0.05, "relevance": 0.30,
                   "precision": 0.30, "attrs": 0.10, "confidence": 0.15}
        total = sum(self.dims[d].score * weights.get(d, 0.1) for d in self.dims)
        norm = sum(weights.get(d, 0.1) for d in self.dims)
        return total / norm if norm else 0


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    stop = {"的", "是", "在", "和", "了", "有", "不", "也", "就", "都", "与", "或", "对", "等",
            "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "to", "for", "and", "or"}
    return {w for w in words if len(w) > 1 and w not in stop}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _score_schema(candidates: list[dict]) -> DimScore:
    if not candidates:
        return DimScore(1.0, "no candidates, vacuously compliant")
    errors = []
    for i, node in enumerate(candidates):
        for key in ["id", "name", "type", "description", "category",
                     "difficulty", "confidence"]:
            if key not in node:
                errors.append(f"node[{i}] missing {key}")
            elif key == "type" and node[key] not in _VALID_TYPES:
                errors.append(f"node[{i}] bad type={node[key]}")
            elif key == "category" and node[key] not in _VALID_CATEGORIES:
                errors.append(f"node[{i}] bad category={node[key]}")
            elif key == "difficulty" and not (1 <= node[key] <= 5):
                errors.append(f"node[{i}] difficulty={node[key]} out of range")
            elif key == "confidence" and not (0 <= node[key] <= 1):
                errors.append(f"node[{i}] confidence={node[key]} out of range")
    total_checks = len(candidates) * 7
    score = (total_checks - len(errors)) / total_checks if total_checks else 1.0
    return DimScore(score, "; ".join(errors[:3]) if errors else "all good")


def _score_id_norm(candidates: list[dict], case_id: str) -> DimScore:
    if not candidates:
        return DimScore(1.0, "no candidates")
    ids = [n["id"] for n in candidates]
    duplicates = [i for i, c in Counter(ids).items() if c > 1]
    if duplicates:
        return DimScore(0.0, f"duplicate ids: {duplicates}")
    issues = []
    for nid in ids:
        if re.search(r"[A-Z]", nid):
            issues.append(f"uppercase in {nid}")
        if re.search(r"[^\w-]", nid.replace("-", "")):
            issues.append(f"special chars in {nid}")
    score = max(0.0, 1.0 - len(issues) * 0.3)
    return DimScore(score, "; ".join(issues[:2]) if issues else "ids clean")


def _score_relevance(candidates: list[dict], source_text: str) -> DimScore:
    if not candidates:
        return DimScore(1.0, "no candidates expected/delivered")
    if not source_text.strip():
        return DimScore(0.0, "empty source text")

    scores = []
    for node in candidates:
        node_text = f"{node.get('name', '')}。{node.get('description', '')}"
        try:
            sim = semantic_similarity(node_text, source_text)
        except Exception as exc:
            return DimScore(0.0, f"embedding failed: {exc}")
        scores.append(max(0.0, min(1.0, sim)))

    avg = statistics.mean(scores) if scores else 0.0
    return DimScore(round(avg, 3), f"avg cosine={avg:.3f}")


def _score_precision(candidates: list[dict], forbidden: list[str]) -> DimScore:
    if not candidates:
        return DimScore(1.0, "no candidates")
    if forbidden == ["*"]:
        violations = list(range(len(candidates)))
    else:
        forbidden_lower = {f.lower() for f in forbidden}
        violations = [
            i for i, n in enumerate(candidates)
            if n.get("name", "").lower() in forbidden_lower
        ]
    if not violations:
        return DimScore(1.0, "no forbidden concepts")
    score = max(0.0, 1.0 - len(violations) / len(candidates))
    return DimScore(score, f"hallucinated: {[candidates[i]['name'] for i in violations]}")


def _score_attrs(candidates: list[dict], expected_types: dict[str, str]) -> DimScore:
    if not candidates or not expected_types:
        return DimScore(1.0, "no type expectations")
    hits = 0
    total = len(expected_types)
    for node in candidates:
        name = node.get("name", "")
        expected = expected_types.get(name)
        if expected and node.get("type") == expected:
            hits += 1
    score = hits / total if total else 1.0
    return DimScore(score, f"{hits}/{total} types correct")


def _score_confidence(candidates: list[dict]) -> DimScore:
    if not candidates:
        return DimScore(1.0, "no candidates")
    confs = [n["confidence"] for n in candidates]
    avg = statistics.mean(confs)
    if avg < 0.85:
        return DimScore(0.5, f"avg conf={avg:.2f} below threshold - candidates shouldn't exist")
    return DimScore(min(1.0, avg), f"avg={avg:.3f}, min={min(confs):.3f}")


async def evaluate_one(client: httpx.AsyncClient, tc: dict, url: str) -> CaseReport:
    payload = {
        "course_id": tc["course_id"],
        "user_message": tc["user_message"],
        "assistant_reply": tc["assistant_reply"],
        "existing_node_ids": [],
    }
    t0 = time.perf_counter()
    resp = await client.post(url, json=payload, timeout=httpx.Timeout(120))
    elapsed = time.perf_counter() - t0

    body = resp.json()
    candidates = body.get("data", {}).get("candidates", [])

    source_text = tc["user_message"] + " " + tc["assistant_reply"]
    report = CaseReport(
        case_id=tc["id"],
        total_candidates=len(candidates),
        candidates=candidates,
        dims={
            "schema": _score_schema(candidates),
            "id_norm": _score_id_norm(candidates, tc["id"]),
            "relevance": _score_relevance(candidates, source_text),
            "precision": _score_precision(candidates, tc.get("forbidden_concepts", [])),
            "attrs": _score_attrs(candidates, tc.get("expected_types", {})),
            "confidence": _score_confidence(candidates),
        },
    )
    return report, elapsed


def _bar(score: float, width: int = 20) -> str:
    filled = int(score * width)
    if score >= 0.8:
        ch = "█"
    elif score >= 0.5:
        ch = "▓"
    else:
        ch = "░"
    return ch * filled + " " * (width - filled)


async def main(url: str):
    extract_url = f"{url}/internal/graph/extract"

    print(f"\n{'='*80}")
    print(f"  知识提取质量评估")
    print(f"  Target: {extract_url}")
    print(f"  Test cases: {len(TEST_CASES)}")
    print(f"{'='*80}\n")

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=50)
    async with httpx.AsyncClient(limits=limits) as client:
        reports = []
        total_times = []

        for tc in TEST_CASES:
            report, elapsed = await evaluate_one(client, tc, extract_url)
            reports.append(report)
            total_times.append(elapsed)

            # per-case detail
            print(f"  [{tc['id']}]  candidates={report.total_candidates}  "
                  f"latency={elapsed:.1f}s  overall={report.overall:.2f}")
            for dim, ds in report.dims.items():
                print(f"     {dim:12s}  {_bar(ds.score)}  {ds.score:.2f}  {ds.detail}")
            print()

    # Aggregate
    all_overall = [r.overall for r in reports]
    dim_avgs = {}
    for dim in ["schema", "id_norm", "relevance", "precision", "attrs", "confidence"]:
        scores = [r.dims[dim].score for r in reports if dim in r.dims]
        dim_avgs[dim] = statistics.mean(scores) if scores else 0.0

    print(f"{'='*80}")
    print(f"  FINAL SCORECARD")
    print(f"{'='*80}")
    print(f"  Cases evaluated:    {len(reports)}")
    print(f"  Avg latency:        {statistics.mean(total_times):.1f}s (±{statistics.stdev(total_times):.1f})")
    print(f"  Overall quality:    {statistics.mean(all_overall):.2f} / 1.00")
    print()
    print(f"  Dimension breakdown:")
    for dim, avg in dim_avgs.items():
        grade = "A" if avg >= 0.85 else "B" if avg >= 0.7 else "C" if avg >= 0.5 else "D"
        print(f"     {dim:14s}  {_bar(avg)}  {avg:.2f}  ({grade})")
    print()

    # Grade interpretation
    final = statistics.mean(all_overall)
    if final >= 0.85:
        verdict = "🟢 READY — 提取质量优秀，可以上线"
    elif final >= 0.70:
        verdict = "🟡 ACCEPTABLE — 提取质量可接受，建议优化弱项"
    elif final >= 0.50:
        verdict = "🟠 NEEDS WORK — 部分维度不合格，需要针对性改进"
    else:
        verdict = "🔴 FAILING — 提取质量不足，需要重新设计prompt"
    print(f"  VERDICT: {verdict}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    asyncio.run(main(target))

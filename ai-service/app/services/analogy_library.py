import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnalogyEntry:
    concept: str
    analogy: str
    explanation: str
    category: str


BUILTIN_ANALOGIES: dict[str, list[AnalogyEntry]] = {
    "ai": [
        AnalogyEntry("神经网络", "神经网络就像大脑中的神经元网络", "每个神经元接收输入信号，处理后传递给下一层", "深度学习"),
        AnalogyEntry("梯度下降", "梯度下降就像蒙眼下山", "每次试探性踏出一步，感受坡度，往最陡的方向走", "优化"),
        AnalogyEntry("过拟合", "过拟合就像死记硬背答案", "记住了所有练习题但考试换一道就不会做", "泛化"),
        AnalogyEntry("卷积", "卷积就像用放大镜扫描图片", "每次只看一小块区域，提取局部特征", "计算机视觉"),
        AnalogyEntry("注意力机制", "注意力就像考试划重点", "不是每个字都同等重要，聚焦关键信息", "Transformer"),
        AnalogyEntry("损失函数", "损失函数就像考试分数", "分数越低说明学得越好（与答案的差距越小）", "优化"),
        AnalogyEntry("正则化", "正则化就像学习中的复习", "防止只记住偏题怪题，保持知识的普适性", "优化"),
        AnalogyEntry("监督学习", "监督学习就像有老师批改的练习", "每道题都有标准答案，做错了老师会纠正", "基础概念"),
        AnalogyEntry("无监督学习", "无监督学习就像自己分类整理书架", "没有标签，自己找出规律来分组", "基础概念"),
        AnalogyEntry("强化学习", "强化学习就像训练宠物", "做对了给奖励，做错了给惩罚，逐步学会最优策略", "基础概念"),
    ],
    "ml": [
        AnalogyEntry("决策树", "决策树就像20问猜词游戏", "每个分支代表一个问题，直到缩小到正确答案", "分类"),
        AnalogyEntry("随机森林", "随机森林就像专家会诊", "多个医生（决策树）各自诊断，投票决定最终结果", "集成学习"),
    ],
    "dl": [
        AnalogyEntry("RNN", "RNN就像读一本小说", "理解当前段落需要记住前面的剧情", "序列模型"),
        AnalogyEntry("LSTM", "LSTM就像选择性记忆的日记", "重要的信息记住，无关紧要的可以忘记", "序列模型"),
    ],
}


class AnalogyLibrary:
    def search(self, concept: str, category: str = "") -> list[AnalogyEntry]:
        results = []
        query_lower = concept.lower()
        for cat, entries in BUILTIN_ANALOGIES.items():
            if category and cat != category:
                continue
            for entry in entries:
                if query_lower in entry.concept.lower() or query_lower in entry.analogy.lower():
                    results.append(entry)
        return results[:3]

    def get_for_concept(self, concept: str) -> AnalogyEntry | None:
        results = self.search(concept)
        return results[0] if results else None

    def get_categories(self) -> list[str]:
        return list(BUILTIN_ANALOGIES.keys())

    def format_for_prompt(self, concept: str) -> str:
        entry = self.get_for_concept(concept)
        if not entry:
            return ""
        return f"【类比】{entry.concept}：{entry.analogy}——{entry.explanation}"


_analogy_lib: AnalogyLibrary | None = None
_analogy_lock = threading.Lock()


def get_analogy_library() -> AnalogyLibrary:
    global _analogy_lib
    if _analogy_lib is None:
        with _analogy_lock:
            if _analogy_lib is None:
                _analogy_lib = AnalogyLibrary()
    return _analogy_lib
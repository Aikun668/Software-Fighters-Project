"""证据域路由：`/evidence/apply` 学习证据记账。

Python 只**算**不落库：校验 `(source_action, type)` 组合 → 幂等判重 → 算出新掌握度。
与 `/graph/masteries` 共用同一 `PlanService.update_mastery` 口径（P1 §3.3 唯一真源）。
"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import EvidenceApplyRequest
from app.services import evidence_contract

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/evidence/apply")
async def apply_learning_evidence(body: EvidenceApplyRequest):
    """提交学习证据 → 校验组合合法性 + 幂等判重 + 计算新掌握度。

    - 非法组合 → 400（P1 §4.3 快速失败，在边界拒绝）；
    - 重复提交 → 200 + `applied=False`（P1 §4.4 规则 1：不报错）；
    - 掌握度只由 Java 落库，Python 返回计算值供其写入。
    """
    ev = body.evidence
    try:
        result = evidence_contract.apply_evidence(
            evidence_id=ev.evidence_id,
            student_id=ev.student_id,
            course_id=ev.course_id,
            node_id=ev.node_id,
            evidence_type=ev.type,
            source_action=ev.source_action,
            source_record_id=ev.source_record_id,
            score_or_result=ev.score_or_result,
            confidence=ev.confidence,
            current_mastery=body.current_mastery,
        )
    except evidence_contract.EvidenceContractError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to apply evidence: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "证据记账失败，请稍后重试", status_code=500)

    return api.api_success(result)

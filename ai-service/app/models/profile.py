from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON, func

from app.db.database import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    knowledge_base = Column(Integer, default=0)
    cognitive_style = Column(String(50))
    learning_goal = Column(String(500))
    weak_points = Column(JSON)
    learning_pace = Column(String(50))
    interest_direction = Column(JSON)
    raw_profile_json = Column(JSON)
    updated_at = Column(DateTime, default=func.now())

    # ── 旧权重系统（保留向后兼容，ARRAY 维度不再使用）──
    tag_weights = Column(JSON, default=dict)
    stability_counter = Column(JSON, default=dict)

    # ── 新条目系统（DeepTutor 风格）──
    # entries: {"weak_points": [{text, evidence_indices, confidence, status, created_at, updated_at}, ...],
    #           "interest_direction": [...]}
    entries = Column(JSON, default=dict)

    # ── 增量提取 & 审计 ──
    last_extracted_msg_index = Column(Integer, default=0)
    audit_counter = Column(Integer, default=0)

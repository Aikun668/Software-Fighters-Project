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
    # 动态权重系统
    tag_weights = Column(JSON, default=dict)  # {"weak_points": {"标签": 0.8}, "interest_direction": {...}}
    stability_counter = Column(JSON, default=dict)  # {"cognitive_style": {"value": "视觉型", "count": 2}}

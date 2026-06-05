from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func

from app.db.database import Base


class LearningPlan(Base):
    __tablename__ = "learning_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(String(50))
    title = Column(String(200))
    status = Column(String(20), default="pending")
    total_steps = Column(Integer)
    completed_steps = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    paused_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("learning_plans.id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    topic = Column(String(200))
    knowledge_node_id = Column(String(50))
    status = Column(String(20), default="pending")
    estimated_days = Column(Integer)
    mastery_before = Column(Float)
    mastery_after = Column(Float)
    topic_difficulty = Column(Integer, default=3)
    mastery_current = Column(Float)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_review_at = Column(DateTime, nullable=True)
    review_count = Column(Integer, default=0)

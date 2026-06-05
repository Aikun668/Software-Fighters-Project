from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func

from app.db.database import Base


class LearningActivity(Base):
    __tablename__ = "learning_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("learning_plans.id"), nullable=True)
    step_id = Column(Integer, ForeignKey("plan_steps.id"), nullable=True)
    activity_type = Column(String(50))
    duration_minutes = Column(Integer)
    score = Column(Float)
    created_at = Column(DateTime, default=func.now())

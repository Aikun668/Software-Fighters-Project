from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, func

from app.db.database import Base


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    progress = Column(Float, default=0.0)
    score = Column(Float)
    time_spent = Column(Integer)
    created_at = Column(DateTime, default=func.now())

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

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func

from app.db.database import Base


class NodeMastery(Base):
    __tablename__ = "node_mastery"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    node_id = Column(String(50), nullable=False)
    course_id = Column(String(50), default="ai_intro")
    mastery = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    last_review_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uk_user_node"),
    )

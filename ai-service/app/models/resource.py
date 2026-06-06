from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON, func

from app.db.database import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(50), nullable=False)
    topic = Column(String(200), nullable=False)
    title = Column(String(300))
    content_json = Column(JSON)
    file_path = Column(String(500))
    created_at = Column(DateTime, default=func.now())

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class DataExport(Base):
    """GDPR data export request tracking."""
    __tablename__ = "data_exports"

    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    file_path = Column(String(512))
    format = Column(String(20), default='json')  # 'json', 'csv'
    status = Column(String(20), default='pending')  # 'pending', 'completed', 'failed'
    expires_at = Column(DateTime(timezone=True))  # Auto-delete after 7 days
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="data_exports")

    __table_args__ = (
        Index('idx_data_exports_user_id', 'user_id'),
        Index('idx_data_exports_status', 'status'),
    )

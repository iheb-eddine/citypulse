from sqlalchemy import Column, Integer, Text, Float, DateTime, Index, CheckConstraint, text
from app.database import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_longitude"),
        CheckConstraint(
            "category IN ('pothole','streetlight','graffiti','flooding','dumping','sign','other','unclassified')",
            name="ck_category",
        ),
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_severity"),
        CheckConstraint(
            "department IN ('roads','electrical','sanitation','water','parks','general')",
            name="ck_department",
        ),
        Index("idx_reports_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    photo_path = Column(Text, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    category = Column(Text, nullable=False)
    severity = Column(Text, nullable=False)
    department = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    cluster_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

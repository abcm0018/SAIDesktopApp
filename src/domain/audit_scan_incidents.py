from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, String, Text

from src.domain.bae import Base


class AuditScanIncidents(Base):
    __tablename__ = 'audit_scan_incidents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)

    employee_number = Column(String(4), nullable=False)
    sscc_attempt = Column(String(100), nullable=True)
    ean_attempt = Column(String(100), nullable=True)
    batch_attempt = Column(String(100), nullable=True)

    incident_type = Column(String(100), default="TIMEOUT_DEMAGED_LABEL", nullable=False)
    details = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AuditScanIncidents(id={self.id}, timestamp={self.timestamp}, employee_number={self.employee_number}, sscc_attempt={self.sscc_attempt}, ean_attempt={self.ean_attempt}, batch_attempt={self.batch_attempt}, incident_type={self.incident_type}, details={self.details})>"
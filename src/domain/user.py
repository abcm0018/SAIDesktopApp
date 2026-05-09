from sqlalchemy import Column, String, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.mysql import BIT

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)
    
    employee_number = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    role = Column(String(50), nullable=False)
    
    _active = Column("active", BIT(1), nullable=False)
    _blocked = Column("blocked", BIT(1), nullable=False)
    
    # PROPIEDADES (Getters inteligentes):
    # Esto convierte lo que venga de la BD (1, 0, b'\x01', b'\x00') a True/False de Python
    @property
    def active(self):
        if isinstance(self._active, bytes):
            return self._active != b'\x00'
        return bool(self._active)

    @property
    def blocked(self):
        if isinstance(self._blocked, bytes):
            return self._blocked != b'\x00'
        return bool(self._blocked)

    def __repr__(self):
        return f"<User(employee={self.employee_number}, active={self.active})>"
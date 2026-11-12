from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

class CuponCreateRequest(BaseModel):
    codigo_cupon: str
    tipo_descuento: str
    valor_descuento: float
    monto_minimo: Optional[float] = 0.0
    limite_usos: Optional[int] = None
    limite_uso_por_usuario: Optional[int] = 1
    fecha_inicio: datetime
    fecha_expiracion: datetime

class CuponUpdateRequest(BaseModel):
    codigo_cupon: Optional[str] = None
    tipo_descuento: Optional[str] = None
    valor_descuento: Optional[float] = None
    monto_minimo: Optional[float] = None
    limite_usos: Optional[int] = None
    limite_uso_por_usuario: Optional[int] = None
    fecha_inicio: Optional[datetime] = None
    fecha_expiracion: Optional[datetime] = None

class CuponResponse(BaseModel):
    id: UUID
    codigo_cupon: str
    tipo_descuento: str
    valor_descuento: float
    monto_minimo: Optional[float] = None
    limite_usos: Optional[int] = None
    limite_uso_por_usuario: Optional[int] = 1
    usos_actuales: Optional[int] = 0
    estado: bool
    fecha_inicio: datetime
    fecha_expiracion: datetime

    class Config:
        from_attributes = True
from pydantic import BaseModel
from typing import Dict, Any, Optional
from uuid import UUID

class RolCreateRequest(BaseModel):
    nombre: str
    permisos: Dict[str, Any]
    estado: Optional[bool] = True

class RolUpdateRequest(BaseModel):
    nombre: str
    permisos: Dict[str, Any]

class RolResponse(BaseModel):
    id: UUID
    nombre: str
    permisos: Optional[Dict[str, Any]] = {}
    estado: bool 
    total_usuarios: Optional[int] = 0

    class Config:
        from_attributes = True
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MarcaResponse(BaseModel):
    id: str
    nombre: str
    slug: str
    descripcion: Optional[str] = None
    imagen_marca: Optional[str] = None
    estado: Optional[bool] = True
    creado_en: Optional[datetime] = None
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CategoriaResponse(BaseModel):
    id: str
    nombre: str
    slug: str
    descripcion: Optional[str] = None
    imagen_categoria: Optional[str] = None
    estado: Optional[bool] = True
    creado_en: Optional[datetime] = None
    cantidad_productos: Optional[int] = 0 
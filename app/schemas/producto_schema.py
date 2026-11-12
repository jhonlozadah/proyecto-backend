from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

class ProductoResponse(BaseModel):
    id: str
    id_categoria: str
    id_marca: str
    nombre: str
    slug: str
    sku: Optional[str] = None
    descripcion_corta: Optional[str] = None
    descripcion_detallada: Optional[str] = None
    precio_normal: float
    precio_oferta: Optional[float] = None
    porcentaje_descuento: Optional[float] = None
    cantidad: Optional[Any] = None
    presentacion: Optional[str] = None
    stock: int
    vida_util: Optional[str] = None
    base_quimica: Optional[str] = None
    aspecto: Optional[str] = None
    densidad: Optional[str] = None
    disolventes: Optional[str] = None
    etiquetas: Optional[str] = None
    url_ficha_tecnica: Optional[str] = None
    imagen_principal: Optional[str] = None
    estado: Optional[bool] = True
    destacado: Optional[bool] = False
    creado_en: Optional[datetime] = None
    categorias: Optional[Any] = None
    marcas: Optional[Any] = None
    producto_imagenes: Optional[Any] = None
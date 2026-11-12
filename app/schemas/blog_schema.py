from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

class BlogCreateRequest(BaseModel):
    id_categoria: UUID
    titulo: str
    subtitulo: str
    primer_descripcion: str
    segunda_descripcion: str
    imagen_principal: str
    imagen_banner: str
    imagen_producto_1: str
    imagen_producto_2: str

class BlogUpdateRequest(BaseModel):
    id_categoria: Optional[UUID] = None
    titulo: Optional[str] = None
    subtitulo: Optional[str] = None
    primer_descripcion: Optional[str] = None
    segunda_descripcion: Optional[str] = None
    imagen_principal: Optional[str] = None
    imagen_banner: Optional[str] = None
    imagen_producto_1: Optional[str] = None
    imagen_producto_2: Optional[str] = None

class BlogResponse(BaseModel):
    id: UUID
    id_usuario: Optional[UUID] = None
    id_categoria: UUID
    titulo: str
    slug: str
    subtitulo: Optional[str] = None
    primer_descripcion: Optional[str] = None
    segunda_descripcion: Optional[str] = None
    imagen_principal: Optional[str] = None
    imagen_banner: Optional[str] = None
    imagen_producto_1: Optional[str] = None
    imagen_producto_2: Optional[str] = None
    estado: bool
    creado_en: datetime
    categorias: Optional[dict] = None

    class Config:
        from_attributes = True

class ComentarioCreateRequest(BaseModel):
    id_blog: UUID
    comentario: str
    parent_id: Optional[UUID] = None

class ComentarioResponse(BaseModel):
    id: UUID
    id_usuario: Optional[UUID] = None 
    id_blog: UUID
    parent_id: Optional[UUID] = None
    comentario: str
    fecha_hora: datetime
    usuarios: Optional[dict] = None

    class Config:
        from_attributes = True
from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional

class UsuarioPerfilResponse(BaseModel):
    id: str
    nombres: str
    apellidos: str
    correo: EmailStr
    telefono: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    razon_social: Optional[str] = None
    direccion: Optional[str] = None
    referencia: Optional[str] = None
    departamento: Optional[str] = None
    provincia: Optional[str] = None
    distrito: Optional[str] = None
    imagen_perfil: Optional[str] = None 

class UsuarioUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    razon_social: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    referencia: Optional[str] = None
    departamento: Optional[str] = None
    provincia: Optional[str] = None
    distrito: Optional[str] = None

class UsuarioPasswordUpdate(BaseModel):
    contrasena_actual: str
    nueva_contrasena: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    rol: str
    mfa_requerido: bool = False

class ValidarMFARequest(BaseModel):
    codigo: str

class CrearUsuarioAdminRequest(BaseModel):
    nombres: str
    apellidos: str
    correo: EmailStr
    rol: str 
    contrasena_usuario: str
    confirmacion_contrasena_admin: str

class UsuarioAdminResponse(BaseModel):
    id: str
    nombres: str
    apellidos: str
    correo: EmailStr
    estado: str 
    rol: str
    mfa_activo: bool
    creado_en: Optional[datetime] = None
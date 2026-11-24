import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional

NOMBRE_REGEX = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$")
REPETICION_REGEX = re.compile(r"(.)\1{2,}", re.IGNORECASE)
PASSWORD_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,128}$")

def limpiar_y_validar_nombre(valor: str, campo: str) -> str:
    limpio = re.sub(r"\s+", " ", valor.strip())
    if len(limpio) < 2:
        raise ValueError(f"El campo '{campo}' debe tener al menos 2 caracteres.")
    if len(limpio) > 50:
        raise ValueError(f"El campo '{campo}' no puede superar los 50 caracteres.")
    if not NOMBRE_REGEX.match(limpio):
        raise ValueError(f"El campo '{campo}' solo puede contener letras y espacios.")
    if REPETICION_REGEX.search(limpio):
        raise ValueError(f"El campo '{campo}' contiene demasiadas letras repetidas seguidas.")
    return limpio

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
    nombres: Optional[str] = Field(None, min_length=2, max_length=50)
    apellidos: Optional[str] = Field(None, min_length=2, max_length=50)
    tipo_documento: Optional[str] = Field(None, max_length=20)
    numero_documento: Optional[str] = Field(None, max_length=20)
    razon_social: Optional[str] = Field(None, max_length=150)
    telefono: Optional[str] = Field(None, max_length=20)
    direccion: Optional[str] = Field(None, max_length=200)
    referencia: Optional[str] = Field(None, max_length=200)
    departamento: Optional[str] = Field(None, max_length=60)
    provincia: Optional[str] = Field(None, max_length=60)
    distrito: Optional[str] = Field(None, max_length=60)

    @field_validator("nombres")
    @classmethod
    def validar_nombres(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return limpiar_y_validar_nombre(v, "nombres")

    @field_validator("apellidos")
    @classmethod
    def validar_apellidos(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return limpiar_y_validar_nombre(v, "apellidos")

class UsuarioPasswordUpdate(BaseModel):
    contrasena_actual: str = Field(..., min_length=1, max_length=128)
    nueva_contrasena: str = Field(..., min_length=8, max_length=128)

    @field_validator("nueva_contrasena")
    @classmethod
    def validar_nueva_contrasena(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(
                "La nueva contraseña debe tener al menos 8 caracteres, una mayúscula, un número y un símbolo especial."
            )
        return v

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    rol: str
    mfa_requerido: bool = False


class ValidarMFARequest(BaseModel):
    codigo: str = Field(..., min_length=4, max_length=10)


class CrearUsuarioAdminRequest(BaseModel):
    nombres: str = Field(..., min_length=2, max_length=50)
    apellidos: str = Field(..., min_length=2, max_length=50)
    correo: EmailStr = Field(..., max_length=100)
    rol: str = Field(..., min_length=2, max_length=30)
    contrasena_usuario: str = Field(..., min_length=8, max_length=128)
    confirmacion_contrasena_admin: str = Field(..., min_length=1, max_length=128)

    @field_validator("nombres")
    @classmethod
    def validar_nombres(cls, v: str) -> str:
        return limpiar_y_validar_nombre(v, "nombres")

    @field_validator("apellidos")
    @classmethod
    def validar_apellidos(cls, v: str) -> str:
        return limpiar_y_validar_nombre(v, "apellidos")

    @field_validator("contrasena_usuario")
    @classmethod
    def validar_contrasena_usuario(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(
                "La contraseña del usuario debe tener al menos 8 caracteres, una mayúscula, un número y un símbolo especial."
            )
        return v

class UsuarioAdminResponse(BaseModel):
    id: str
    nombres: str
    apellidos: str
    correo: EmailStr
    estado: str
    rol: str
    mfa_activo: bool
    creado_en: Optional[datetime] = None
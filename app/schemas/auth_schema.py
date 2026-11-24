import re
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


class LoginRequest(BaseModel):
    correo: EmailStr = Field(..., max_length=100)
    contrasena: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    rol: str
    mfa_requerido: bool = False


class ValidarMFARequest(BaseModel):
    codigo: str = Field(..., min_length=4, max_length=10)


class RegisterRequest(BaseModel):
    correo: EmailStr = Field(..., max_length=100)
    contrasena: str = Field(..., min_length=8, max_length=128)
    nombres: str = Field(..., min_length=2, max_length=50)
    apellidos: str = Field(..., min_length=2, max_length=50)
    recaptcha_token: str = Field(..., min_length=1)

    @field_validator("nombres")
    @classmethod
    def validar_nombres(cls, v: str) -> str:
        return limpiar_y_validar_nombre(v, "nombres")

    @field_validator("apellidos")
    @classmethod
    def validar_apellidos(cls, v: str) -> str:
        return limpiar_y_validar_nombre(v, "apellidos")

    @field_validator("contrasena")
    @classmethod
    def validar_contrasena(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(
                "La contraseña debe tener al menos 8 caracteres, una mayúscula, un número y un símbolo especial."
            )
        return v


class RecuperarEnviarRequest(BaseModel):
    email: EmailStr = Field(..., max_length=100)


class RecuperarVerificarRequest(BaseModel):
    email: EmailStr = Field(..., max_length=100)
    codigo: str = Field(..., min_length=4, max_length=10)


class RecuperarCambiarRequest(BaseModel):
    nueva_password: str = Field(..., min_length=8, max_length=128)
    access_token: str = Field(..., min_length=1)

    @field_validator("nueva_password")
    @classmethod
    def validar_nueva_password(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(
                "La nueva contraseña debe tener al menos 8 caracteres, una mayúscula, un número y un símbolo especial."
            )
        return v
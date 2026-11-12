from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    rol: str
    mfa_requerido: bool = False

class ValidarMFARequest(BaseModel):
    codigo: str

class RegisterRequest(BaseModel):
    correo: EmailStr
    contrasena: str
    nombres: str
    apellidos: str
    recaptcha_token: str

class RecuperarEnviarRequest(BaseModel):
    email: EmailStr

class RecuperarVerificarRequest(BaseModel):
    email: EmailStr
    codigo: str

class RecuperarCambiarRequest(BaseModel):
    nueva_password: str
    access_token: str
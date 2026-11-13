import random
import string
import math
import requests
from pydantic import BaseModel
from fastapi import Response, Cookie
from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.core.config import settings
from app.api.dependencies import obtener_usuario_actual
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.schemas.auth_schema import RecuperarEnviarRequest, RecuperarVerificarRequest, RecuperarCambiarRequest, RegisterRequest, LoginRequest, LoginResponse, ValidarMFARequest
from app.services.email_brevo import enviar_correo_recuperacion
from app.core.database import supabase, supabase_admin, get_redis
from redis.asyncio import Redis
from datetime import datetime, timedelta
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import Request
from app.services.notificaciones_service import notificar_administradores

router = APIRouter()
security = HTTPBearer()
intentos_login = {}
codigos_recuperacion = {}
intentos_recuperacion = {}

MAX_INTENTOS = 3            
TIEMPO_BLOQUEO_MINUTOS = 15 

class RecuperarPasswordRequest(BaseModel):
    email: str

class VerificarCodigoRequest(BaseModel):
    email: str
    codigo: str

class NuevaPasswordRequest(BaseModel):
    nueva_password: str
    access_token: str 

class TokenBody(BaseModel):
    token: str

@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, response: Response, request: Request):
    ip_cliente = request.client.host
    ahora = datetime.utcnow()
    registro = intentos_login.get(ip_cliente, {"intentos": 0, "bloqueado_hasta": None})
    if registro["bloqueado_hasta"] and ahora < registro["bloqueado_hasta"]:
        segundos_restantes = math.ceil((registro["bloqueado_hasta"] - ahora).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Inténtalo de nuevo en {segundos_restantes} segundos."
        )
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.correo,
            "password": credentials.contrasena
        })

        if ip_cliente in intentos_login:
            del intentos_login[ip_cliente]

        user_id = auth_response.user.id
        usuario_db = supabase_admin.table("usuarios").select("roles(nombre), mfa_activo").eq("id", user_id).single().execute()
        rol_nombre = "cliente"
        mfa_requerido = False
        if usuario_db.data:
            if usuario_db.data.get("roles"):
                rol_nombre = usuario_db.data["roles"]["nombre"].lower()
            if usuario_db.data.get("mfa_activo"):
                mfa_requerido = True

        token = auth_response.session.access_token

        if not mfa_requerido:
            response.set_cookie(key="access_token", value=token, httponly=True, secure=True, samesite="none", path="/", max_age=3600)

        return LoginResponse(
            access_token=token,
            refresh_token=auth_response.session.refresh_token,
            rol=rol_nombre,
            mfa_requerido=mfa_requerido
        )
    
    except Exception as e:
        registro["intentos"] += 1
        if registro["intentos"] >= 3:
            multiplicador = 2 ** (registro["intentos"] - 3) 
            minutos_bloqueo = 1 * multiplicador
            registro["bloqueado_hasta"] = ahora + timedelta(minutes=minutos_bloqueo)
            intentos_login[ip_cliente] = registro

            raise HTTPException(
                status_code=429,
                detail=f"Cuenta bloqueada por seguridad. Espera {minutos_bloqueo * 60} segundos."
            )
        else:
            intentos_login[ip_cliente] = registro
            intentos_restantes = 3 - registro["intentos"]
            raise HTTPException(
                status_code=401,
                detail=f"Correo o contraseña incorrectos. Te quedan {intentos_restantes} intento(s)."
            )

@router.post("/mfa/validar-login")
def validar_mfa_login(
    datos: ValidarMFARequest, 
    credentials: HTTPAuthorizationCredentials = Depends(security) 
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Token temporal no proporcionado.")

    access_token = credentials.credentials
    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        url_user = f"{settings.SUPABASE_URL}/auth/v1/user"
        res_user = requests.get(url_user, headers=headers)

        if res_user.status_code >= 400:
            raise ValueError("Sesión temporal expirada o inválida.")

        user_data = res_user.json()
        factores = user_data.get("factors", [])
        factor_totp = next((f for f in factores if f["factor_type"] == "totp" and f["status"] == "verified"), None)
        
        if not factor_totp:
            raise ValueError("MFA no está configurado correctamente.")
        
        factor_id = factor_totp["id"]
        url_challenge = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id}/challenge"
        challenge_id = requests.post(url_challenge, headers=headers).json()["id"]
        url_verify = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id}/verify"
        res_verify = requests.post(url_verify, headers=headers, json={
            "challenge_id": challenge_id, 
            "code": datos.codigo
        })
        
        if res_verify.status_code >= 400:
            raise ValueError("Código MFA incorrecto o expirado.")
        
        verify_data = res_verify.json()
        nuevo_token = verify_data.get("access_token")
        
        return {
            "mensaje": "Validación MFA exitosa",
            "access_token": nuevo_token
        }

    except Exception as e:
        print(f"[DEBUG MFA VERIFY] Error: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_data: RegisterRequest, response: Response):
    recaptcha_url = "https://www.google.com/recaptcha/api/siteverify"
    recaptcha_data = {
        "secret": settings.RECAPTCHA_SECRET_KEY,
        "response": user_data.recaptcha_token
    }

    google_response = requests.post(recaptcha_url, data=recaptcha_data).json()

    if not google_response.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La validación de reCAPTCHA falló. Intenta de nuevo."
        )

    rol_fijo = "cliente"

    try:
        rol_response = supabase.table("roles").select("id").ilike("nombre", rol_fijo).execute()
        if not rol_response.data:
            raise HTTPException(status_code=500, detail="Error interno: Rol base no encontrado.")
            
        rol_id = rol_response.data[0]["id"]
        auth_response = supabase.auth.sign_up({
            "email": user_data.correo,
            "password": user_data.contrasena
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=400, detail="No se pudo crear el usuario.")

        user_id = auth_response.user.id

        nuevo_usuario = {
            "id": user_id,
            "id_rol": rol_id,
            "nombres": user_data.nombres,
            "apellidos": user_data.apellidos,
            "correo": user_data.correo,
            "mfa_activo": False
        }

        supabase.table("usuarios").insert(nuevo_usuario).execute()

        try:
            notificar_administradores(
                tipo="usuario",
                titulo="Nuevo Usuario Registrado",
                mensaje=f"{user_data.nombres} {user_data.apellidos} ha creado una cuenta con el correo {user_data.correo}.",
                enlace="usuarios.html"
            )

        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] No se pudo alertar el registro: {e}")

        if auth_response.session:
            response.set_cookie(
                key="access_token",
                value=auth_response.session.access_token,
                httponly=True,
                secure=True,
                samesite="none",
                path="/",
                max_age=3600
        )

        return {
            "mensaje": "Usuario registrado exitosamente",
            "usuario_id": user_id,
            "rol": rol_fijo 
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al registrar: {str(e)}"
        )

@router.post("/recuperar-password/enviar")
def enviar_codigo_recuperacion(datos: RecuperarEnviarRequest):
    email = datos.email.lower().strip()
    verificar_rate_limit(email)
    usuario_db = supabase.table("usuarios").select("id, correo").eq("correo", email).execute()

    if not usuario_db.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una cuenta registrada con este correo electrónico."
        )

    user_id = usuario_db.data[0]["id"]
    codigo_otp = ''.join(random.choices(string.digits, k=6))
    codigos_recuperacion[email] = {
        "codigo": codigo_otp,
        "expira": datetime.utcnow() + timedelta(minutes=15),
        "user_id": user_id
    }

    correo_enviado = enviar_correo_recuperacion(email, codigo_otp)
    if not correo_enviado:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error al enviar el correo. Por favor, inténtalo más tarde."
        )
    return {"mensaje": "Código de verificación enviado con éxito."}

def verificar_rate_limit(email: str):
    ahora = datetime.utcnow()
    registro = intentos_recuperacion.get(email)

    if registro:
        if registro.get("bloqueado_hasta") and ahora < registro["bloqueado_hasta"]:
            minutos_restantes = int((registro["bloqueado_hasta"] - ahora).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Has superado el límite de intentos. Por favor, reintenta en {minutos_restantes} minuto(s)."
            )
        
        if registro.get("bloqueado_hasta") and ahora >= registro["bloqueado_hasta"]:
            intentos_recuperacion[email] = {"intentos": 1, "bloqueado_hasta": None}
            return

        registro["intentos"] += 1
        if registro["intentos"] >= MAX_INTENTOS:
            registro["bloqueado_hasta"] = ahora + timedelta(minutes=TIEMPO_BLOQUEO_MINUTOS)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Límite de solicitudes superado ({MAX_INTENTOS} intentos). Inténtalo de nuevo en {TIEMPO_BLOQUEO_MINUTOS} minutos."
            )
    else:
        intentos_recuperacion[email] = {"intentos": 1, "bloqueado_hasta": None}

@router.post("/recuperar-password/verificar")
def verificar_codigo_recuperacion(datos: RecuperarVerificarRequest):
    registro = codigos_recuperacion.get(datos.email)
    if not registro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No se ha solicitado ningún código o la sesión ha expirado."
        )
    if datetime.utcnow() > registro["expira"]:
        del codigos_recuperacion[datos.email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="El código de verificación ha expirado."
        )
    if registro["codigo"] != datos.codigo.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Código de verificación incorrecto."
        )
    token_temporal = registro["user_id"]
    return {
        "mensaje": "Código verificado exitosamente.",
        "access_token": token_temporal
    }

@router.post("/recuperar-password/cambiar")
def cambiar_password_recuperacion(datos: RecuperarCambiarRequest):
    user_id = datos.access_token
    
    try:
        res = supabase_admin.auth.admin.update_user_by_id(
            user_id,
            {"password": datos.nueva_password}
        )
        
        for email, info in list(codigos_recuperacion.items()):
            if info["user_id"] == user_id:
                del codigos_recuperacion[email]
                break
                
        return {"mensaje": "Contraseña restablecida exitosamente."}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al actualizar la contraseña: {str(e)}"
        )

@router.get("/google")
def login_con_google():
    try:
        res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": "http://127.0.0.1:8000/api/v1/auth/callback" 
            }
        })
        return {"url": res.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error iniciando OAuth: {str(e)}")

@router.get("/callback")
def google_callback(code: str):
    try:
        res = supabase.auth.exchange_code_for_session({"auth_code": code})
        token = res.session.access_token
        user = res.user
        usuario_db = supabase.table("usuarios").select("id, mfa_activo").eq("id", user.id).execute()
        mfa_requerido = False
        
        if not usuario_db.data:
            nombres_google = user.user_metadata.get("full_name", "Usuario")
            rol_fijo = "cliente"
            rol_response = supabase.table("roles").select("id").ilike("nombre", rol_fijo).execute()
            if not rol_response.data:
                raise HTTPException(status_code=500, detail="Error interno: Rol base no encontrado.")
                
            rol_id = rol_response.data[0]["id"]
            supabase.table("usuarios").insert({
                "id": user.id,
                "id_rol": rol_id,
                "nombres": nombres_google,
                "apellidos": "",
                "correo": user.email,
                "mfa_activo": False
            }).execute()

            try:
                notificar_administradores(
                    tipo="usuario",
                    titulo="Nuevo Usuario (Google)",
                    mensaje=f"{nombres_google} se ha registrado usando su cuenta de Google ({user.email}).",
                    enlace="usuarios.html"
                )
            except Exception as e:
                print(f"[ERROR NOTIFICACIÓN] No se pudo alertar el registro por Google: {e}")
        else:
            mfa_requerido = usuario_db.data[0].get("mfa_activo", False)
        pagina_destino = "main/verificacion.html" if mfa_requerido else "main/perfil-de-usuario.html"
        url_frontend = f"http://127.0.0.1:5500/{pagina_destino}?token={token}"
        respuesta = RedirectResponse(url=url_frontend, status_code=302)
        respuesta.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=True, # Cambiar a True en producción con HTTPS
            samesite="none",
            path="/",
            max_age=3600
        )
        return respuesta
        
    except Exception as e:
        print(f"[ERROR CALLBACK]: {str(e)}")
        raise HTTPException(status_code=400, detail="Error en Auth Google")

@router.post("/sincronizar-sesion")
def sincronizar_sesion(body: TokenBody, response: Response):
    response.set_cookie(
        key="access_token",
        value=body.token,
        httponly=True,
        secure=True, 
        samesite="none",
        path="/",
        max_age=3600
    )
    return {"exito": True}

@router.post("/logout")
async def cerrar_sesion(
    request: Request,
    redis_client: Redis = Depends(get_redis)
):
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    if token:
        await redis_client.setex(f"blacklist:{token}", 3600, "revoked")
        print("[DEBUG AUTH] Token añadido a la lista negra.")

    respuesta = JSONResponse(content={"mensaje": "Sesión cerrada exitosamente y token revocado"})
    respuesta.delete_cookie(key="access_token", path="/", httponly=True, secure=True, samesite="none")
    respuesta.delete_cookie(key="refresh_token", path="/", httponly=True, secure=True, samesite="none")
    respuesta.delete_cookie(key="access_token", path="/", httponly=True, secure=True, samesite="none")

    return respuesta

@router.get("/me")
def obtener_perfil_usuario(usuario_id: str = Depends(obtener_usuario_actual)):
    print(f"[DEBUG AUTH /ME] Procesando perfil para usuario_id: {usuario_id}")
    try:
        res = supabase_admin.table("usuarios") \
            .select("*, roles(nombre, permisos)") \
            .eq("id", usuario_id) \
            .single() \
            .execute()

        if not res.data:
            print(f"[DEBUG AUTH /ME] ❌ No se encontró registro en tabla 'usuarios' para ID: {usuario_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Usuario no encontrado en la base de datos."
            )

        usuario = res.data
        nombre_rol = "cliente"
        permisos = {}
        if usuario.get("roles"): 
            nombre_rol = usuario["roles"].get("nombre", "cliente").lower()
            permisos = usuario["roles"].get("permisos") or {}

        roles_panel_admin = ["administrador", "admin", "vendedor", "diseñador", "gestor"]
        acceso_panel = nombre_rol in roles_panel_admin

        print(f"[DEBUG AUTH /ME] Rol detectado: '{nombre_rol}' | ¿Tiene acceso al panel?: {acceso_panel}")

        return {
            "id": usuario["id"],
            "nombres": usuario.get("nombres", ""),
            "apellidos": usuario.get("apellidos", ""),
            "correo": usuario.get("correo", ""),
            "rol": nombre_rol,
            "es_admin_panel": acceso_panel,
            "permisos": permisos
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[DEBUG AUTH /ME] ❌ Error inesperado: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error al obtener sesión: {str(e)}"
        )
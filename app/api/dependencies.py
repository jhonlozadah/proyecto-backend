import hashlib
from fastapi import HTTPException, status, Depends, Cookie, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.security import decode_jwt_payload
from app.core.database import supabase_admin, get_redis, crear_cliente_auth
import asyncio

security = HTTPBearer(auto_error=False)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]

async def obtener_usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    access_token_cookie: str = Cookie(None, alias="access_token"),
    redis_client: Redis = Depends(get_redis)
) -> str:
    token = credentials.credentials if credentials else access_token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se encontró una sesión activa."
        )

    token_id = _hash_token(token)
    cache_key = f"auth_ok:{token_id}"

    try:
        pipe = redis_client.pipeline()
        pipe.get(f"blacklist:{token}")
        pipe.get(cache_key)
        is_blacklisted, cached_user_id = await pipe.execute()

        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La sesión ha sido cerrada previamente."
            )

        if cached_user_id:
            return cached_user_id.decode() if isinstance(cached_user_id, bytes) else str(cached_user_id)

    except HTTPException:
        raise
    except RedisError as re_err:
        print(f"[REDIS WARNING] Caché/blacklist omitida por conexión: {re_err}")

    try:
        auth_client = crear_cliente_auth()
        user_response = await asyncio.to_thread(auth_client.auth.get_user, token)
        
        if not user_response or not user_response.user:
            raise ValueError("Token inválido")

        user_id = user_response.user.id
        usuario_db = await asyncio.to_thread(
            lambda: supabase_admin.table("usuarios").select("mfa_activo").eq("id", user_id).single().execute()
        )

        if usuario_db.data and usuario_db.data.get("mfa_activo"):
            payload = decode_jwt_payload(token)
            aal_level = payload.get("aal", "aal1")
            if aal_level != "aal2":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Acceso denegado: Debes completar la verificación MFA."
                )
        try:
            await redis_client.setex(cache_key, 60, user_id)
        except RedisError:
            pass

        return user_id

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "10035" in error_msg or "socket" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Saturación de red. Reintente."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o expirada."
        )

async def obtener_usuario_admin(usuario_id: str = Depends(obtener_usuario_actual)) -> str:
    try:
        usuario_db = supabase_admin.table("usuarios") \
            .select("roles(nombre)") \
            .eq("id", usuario_id) \
            .single() \
            .execute()

        if not usuario_db.data or not usuario_db.data.get("roles"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para acceder a este recurso."
            )

        rol_nombre = usuario_db.data["roles"]["nombre"].lower()
        if rol_nombre not in ["administrador", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado. Se requieren permisos de administrador."
            )

        return usuario_id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al verificar los permisos del usuario."
        )


def verificar_permiso(clave_permiso: str):
    async def usuario_tiene_permiso(usuario_id: str = Depends(obtener_usuario_actual)):
        res = supabase_admin.table("usuarios") \
            .select("roles(nombre, permisos)") \
            .eq("id", usuario_id) \
            .single() \
            .execute()

        if not res.data or not res.data.get("roles"):
            raise HTTPException(status_code=403, detail="Acceso denegado. Sin rol asignado.")

        datos_rol = res.data["roles"]
        if isinstance(datos_rol, list):
            datos_rol = datos_rol[0] if datos_rol else {}

        rol_nombre = datos_rol.get("nombre", "").lower()
        permisos = datos_rol.get("permisos") or {}

        if rol_nombre in ["admin", "administrador"]:
            return usuario_id

        clave_alt = clave_permiso.replace("diseños", "disenos").replace("notificaciones", "notificacion")
        tiene_acceso = permisos.get(clave_permiso, False) or permisos.get(clave_alt, False)

        if not tiene_acceso:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permiso para realizar esta acción ({clave_permiso})."
            )
        return usuario_id
    return usuario_tiene_permiso


def rate_limiter(max_requests: int = 10, window_seconds: int = 60):
    async def _rate_limit(
        request: Request,
        redis_client: Redis = Depends(get_redis)
    ):
        identificador = request.client.host if request.client else "unknown"
        token = request.cookies.get("access_token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if token:
            identificador = _hash_token(token)

        key = f"rl:{request.url.path}:{identificador}"

        try:
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            current_requests, _ = await pipe.execute()

            if current_requests > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Estás realizando acciones muy rápido. Espera unos segundos."
                )
        except HTTPException:
            raise
        except RedisError as re_err:
            print(f"[REDIS WARNING] Rate limit omitido por conexión: {re_err}")

    return _rate_limit
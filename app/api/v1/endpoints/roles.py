from typing import List
import traceback
from app.services.notificaciones_service import notificar_administradores
import json
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis
from fastapi import APIRouter, HTTPException, status, Depends
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import verificar_permiso, rate_limiter
from app.schemas.roles_schema import RolCreateRequest, RolUpdateRequest, RolResponse

router = APIRouter()

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

async def limpiar_cache_roles(redis_client: Redis):
    await redis_client.delete("cache:admin:roles_lista")

@router.get("/", response_model=List[RolResponse], dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def listar_roles(
    usuario_id: str = Depends(verificar_permiso("roles_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:roles_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res_roles = supabase_admin.table("roles").select("*").execute()
        res_usuarios = supabase_admin.table("usuarios").select("id_rol").execute()

        conteo_map = {}
        for u in (res_usuarios.data or []):
            r_id = u.get("id_rol")
            if r_id:
                conteo_map[r_id] = conteo_map.get(r_id, 0) + 1

        resultado = []
        for r in (res_roles.data or []):
            resultado.append(RolResponse(
                id=r["id"],
                nombre=r["nombre"],
                permisos=r.get("permisos") or {},
                estado=r.get("estado", True), 
                total_usuarios=conteo_map.get(r["id"], 0)
            ))
            
        await redis_client.setex(cache_key, 900, json.dumps(jsonable_encoder(resultado)))
        return resultado
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print("\n🚨 ERROR CRÍTICO EN MÓDULO DE ROLES 🚨")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al listar roles: {str(e)}")
    
@router.post("/", status_code=status.HTTP_201_CREATED)
async def crear_rol(
    datos: RolCreateRequest, 
    usuario_id: str = Depends(verificar_permiso("roles_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        nuevo = {
            "nombre": datos.nombre.strip(),
            "permisos": datos.permisos,
            "estado": datos.estado if datos.estado is not None else True 
        }
        res = supabase_admin.table("roles").insert(nuevo).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nuevo Rol Creado",
                mensaje=f"{autor} ha creado el rol de usuario '{datos.nombre.strip()}'.",
                enlace="roles.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
            
        await limpiar_cache_roles(redis_client)
        return {"mensaje": "Rol creado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear rol: {str(e)}")

@router.put("/{rol_id}")
async def actualizar_rol(
    rol_id: str, 
    datos: RolUpdateRequest, 
    usuario_id: str = Depends(verificar_permiso("roles_edit")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        datos_actualizar = {
            "nombre": datos.nombre.strip(),
            "permisos": datos.permisos
        }

        respuesta = supabase_admin.table("roles").update(datos_actualizar).eq("id", rol_id).execute()

        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
            
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Permisos de Rol Modificados",
                mensaje=f"{autor} ha actualizado los permisos para el rol '{datos.nombre.strip()}'.",
                enlace="roles.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await limpiar_cache_roles(redis_client)
        return {"mensaje": "Rol actualizado exitosamente", "data": respuesta.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar el rol: {str(e)}")

@router.put("/toggle-estado/{rol_id}")
async def alternar_estado_rol(
    rol_id: str, 
    usuario_id: str = Depends(verificar_permiso("roles_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        rol = supabase_admin.table("roles").select("estado, nombre").eq("id", rol_id).single().execute()
        if not rol.data:
            raise HTTPException(status_code=404, detail="Rol no encontrado")

        nombre_rol = rol.data.get("nombre", "Desconocido")
        
        if nombre_rol.lower() in ["admin", "administrador"]:
            raise HTTPException(
                status_code=400, 
                detail="El rol principal de Administrador no puede ser desactivado."
            )

        nuevo_estado = not rol.data.get("estado", True)
        supabase_admin.table("roles").update({"estado": nuevo_estado}).eq("id", rol_id).execute()

        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "activado" if nuevo_estado else "desactivado"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Rol {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} el rol de usuario '{nombre_rol}'.",
                enlace="roles.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await limpiar_cache_roles(redis_client)
        return {"mensaje": "Estado actualizado", "nuevo_estado": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al cambiar estado del rol: {str(e)}")
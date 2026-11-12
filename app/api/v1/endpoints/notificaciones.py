from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
import json
from redis.asyncio import Redis
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import obtener_usuario_actual, verificar_permiso, rate_limiter

router = APIRouter()

async def limpiar_cache_notificaciones(usuario_id: str, redis_client: Redis):
    await redis_client.delete(f"cache:notificaciones:header:{usuario_id}")
    await redis_client.delete(f"cache:notificaciones:lista:{usuario_id}")

@router.get("/admin/header", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def notificaciones_header(
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:notificaciones:header:{usuario_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        recientes = supabase_admin.table("notificaciones").select("*") \
            .eq("id_usuario", usuario_id).eq("leido", False) \
            .order("fecha_creacion", desc=True).limit(3).execute()
        
        conteo = supabase_admin.table("notificaciones").select("id", count="exact") \
            .eq("id_usuario", usuario_id).eq("leido", False).execute()
        
        respuesta = {
            "total_sin_leer": conteo.count if conteo.count else 0,
            "recientes": recientes.data or []
        }
        
        await redis_client.setex(cache_key, 60, json.dumps(respuesta))
        return respuesta
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/admin")
async def listar_notificaciones(
    tipo: Optional[str] = None, 
    estado: Optional[str] = None, 
    fecha: Optional[str] = None, 
    usuario_id: str = Depends(verificar_permiso("notificaciones_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:notificaciones:lista:{usuario_id}:{tipo or 'all'}:{estado or 'all'}:{fecha or 'all'}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        query = supabase_admin.table("notificaciones").select("*") \
            .eq("id_usuario", usuario_id).order("fecha_creacion", desc=True)
        if tipo:
            query = query.eq("tipo", tipo)
        if estado == "read":
            query = query.eq("leido", True)
        elif estado == "unread":
            query = query.eq("leido", False)
        if fecha:
            query = query.gte("fecha_creacion", f"{fecha}T00:00:00").lte("fecha_creacion", f"{fecha}T23:59:59")
            
        res = query.execute()
        data = res.data or []
        
        await redis_client.setex(cache_key, 300, json.dumps(data))
        return data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/admin/{id}/toggle")
async def toggle_notificacion(
    id: str, 
    usuario_id: str = Depends(verificar_permiso("notificaciones_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        actual = supabase_admin.table("notificaciones").select("leido, id_usuario").eq("id", id).execute()
        
        if not actual.data:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")

        if actual.data[0]["id_usuario"] != usuario_id:
            raise HTTPException(status_code=403, detail="No tienes autorización sobre esta notificación")

        nuevo_estado = not actual.data[0]["leido"]
        supabase_admin.table("notificaciones").update({"leido": nuevo_estado}).eq("id", id).execute()
        await limpiar_cache_notificaciones(usuario_id, redis_client)
        return {"mensaje": "Estado actualizado", "leido": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/admin/marcar-todas")
async def marcar_todas_leidas(
    usuario_id: str = Depends(verificar_permiso("notificaciones_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        supabase_admin.table("notificaciones").update({"leido": True}) \
            .eq("id_usuario", usuario_id).eq("leido", False).execute()
        await limpiar_cache_notificaciones(usuario_id, redis_client)
        return {"mensaje": "Todas las notificaciones marcadas como leídas"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin/{id}")
async def eliminar_notificacion(
    id: str, 
    usuario_id: str = Depends(verificar_permiso("notificaciones_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        res = supabase_admin.table("notificaciones").delete().eq("id", id).eq("id_usuario", usuario_id).execute()
        await limpiar_cache_notificaciones(usuario_id, redis_client)
        return {"mensaje": "Notificación eliminada"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/admin/borrar-todas/historial")
async def limpiar_historial(
    usuario_id: str = Depends(verificar_permiso("notificaciones_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        supabase_admin.table("notificaciones").delete().eq("id_usuario", usuario_id).execute()
        await limpiar_cache_notificaciones(usuario_id, redis_client)
        return {"mensaje": "Historial limpiado"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
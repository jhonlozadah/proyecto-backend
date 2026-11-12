from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, status
from app.services.cloud_storage import subir_imagen
from typing import Optional
from app.services.notificaciones_service import notificar_administradores
import json
from redis.asyncio import Redis
from app.core.database import supabase, supabase_admin, get_redis
from app.api.dependencies import verificar_permiso, rate_limiter

router = APIRouter()
async def limpiar_cache_disenos(redis_client: Redis):
    await redis_client.delete("cache:disenos:publicos")
    await redis_client.delete("cache:admin:disenos_lista")

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

@router.get("/publicos", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_disenos_publicos(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:disenos:publicos"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        response = supabase_admin.table("disenos").select("*").eq("estado", True).order("orden", desc=False).execute()
        
        if response.data:
            await redis_client.setex(cache_key, 1800, json.dumps(response.data))
            
        return response.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener diseños públicos: {str(e)}")

@router.get("/admin")
async def obtener_todos_disenos(
    usuario_id: str = Depends(verificar_permiso("disenos_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:disenos_lista"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        response = supabase_admin.table("disenos").select("*").order("creado_en", desc=True).execute()
        if response.data:
            await redis_client.setex(cache_key, 900, json.dumps(response.data))
            
        return response.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar diseños: {str(e)}")

@router.post("/admin", status_code=status.HTTP_201_CREATED)
async def crear_diseno(
    seccion: str = Form(...),
    nombre: str = Form(...),
    alt_text: str = Form(""),
    enlace: str = Form(""),
    descripcion: str = Form(""),
    orden: int = Form(0), 
    imagen: UploadFile = File(...),
    usuario_id: str = Depends(verificar_permiso("disenos_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        contenido = await imagen.read()
        url_imagen = subir_imagen(contenido)

        nuevo_diseno = {
            "id_usuario": usuario_id,
            "seccion": seccion,
            "nombre": nombre,
            "alt_text": alt_text,
            "enlace": enlace,
            "descripcion": descripcion,
            "orden": orden,
            "url_imagen": url_imagen,
            "estado": True
        }

        res = supabase_admin.table("disenos").insert(nuevo_diseno).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nuevo Diseño Subido",
                mensaje=f"{autor} ha subido el diseño '{nombre}' para la sección '{seccion}'.",
                enlace="disenos.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_disenos(redis_client)
        return {"mensaje": "Diseño creado exitosamente", "data": res.data[0] if res.data else None}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear el diseño: {str(e)}")

@router.put("/admin/{id_diseno}")
async def editar_diseno(
    id_diseno: str,
    seccion: str = Form(...),
    nombre: str = Form(...),
    alt_text: str = Form(""),
    enlace: str = Form(""),
    descripcion: str = Form(""),
    orden: int = Form(0),
    imagen: Optional[UploadFile] = File(None),
    usuario_id: str = Depends(verificar_permiso("disenos_edit")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        datos_actualizar = {
            "seccion": seccion,
            "nombre": nombre,
            "alt_text": alt_text,
            "enlace": enlace,
            "descripcion": descripcion,
            "orden": orden
        }

        if imagen and imagen.filename:
            contenido = await imagen.read()
            url_imagen = subir_imagen(contenido)
            datos_actualizar["url_imagen"] = url_imagen

        res = supabase_admin.table("disenos").update(datos_actualizar).eq("id", id_diseno).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="Diseño no encontrado")

        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Diseño Modificado",
                mensaje=f"{autor} ha modificado las propiedades del diseño '{nombre}'.",
                enlace="disenos.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_disenos(redis_client)
        return {"mensaje": "Diseño actualizado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar el diseño: {str(e)}")

@router.put("/admin/{id_diseno}/estado")
async def alternar_estado_diseno(
    id_diseno: str, 
    usuario_id: str = Depends(verificar_permiso("disenos_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        diseno_db = supabase_admin.table("disenos").select("estado, nombre").eq("id", id_diseno).single().execute()
        if not diseno_db.data:
            raise HTTPException(status_code=404, detail="Diseño no encontrado")

        nuevo_estado = not diseno_db.data.get("estado", True)
        nombre_diseno = diseno_db.data.get("nombre", "Desconocido")
        supabase_admin.table("disenos").update({"estado": nuevo_estado}).eq("id", id_diseno).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "visible" if nuevo_estado else "ocultado"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Diseño {accion.capitalize()}",
                mensaje=f"{autor} ha hecho {accion} el diseño '{nombre_diseno}'.",
                enlace="disenos.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_disenos(redis_client)
        return {
            "mensaje": f"Estado cambiado a {'Visible' if nuevo_estado else 'Oculto'}", 
            "nuevo_estado": nuevo_estado
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al cambiar el estado: {str(e)}")
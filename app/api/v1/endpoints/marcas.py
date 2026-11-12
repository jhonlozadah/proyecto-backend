from app.schemas.marca_schema import MarcaResponse
import re
import json
from redis.asyncio import Redis
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from app.core.database import supabase, supabase_admin, get_redis
from app.api.dependencies import verificar_permiso, rate_limiter
from app.schemas.marca_schema import MarcaResponse
from app.services.cloud_storage import subir_imagen
from app.services.notificaciones_service import notificar_administradores

router = APIRouter()

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception as e:
        print(f"[DEBUG MARCAS] No se pudo obtener el nombre del usuario: {e}")
    return "Un administrador"

def generar_slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[\s_-]+', '-', texto)

async def limpiar_cache_marcas(redis_client: Redis):
    await redis_client.delete("cache:marcas:publicas")
    await redis_client.delete("cache:admin:marcas_lista")

@router.get("/", response_model=list[MarcaResponse])
async def listar_marcas_admin(
    usuario_id: str = Depends(verificar_permiso("marcas_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:marcas_lista"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("marcas").select("*").order("creado_en", desc=True).execute()
        
        if respuesta.data:
            await redis_client.setex(cache_key, 900, json.dumps(respuesta.data))
            
        return respuesta.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/publicas", response_model=list[MarcaResponse], dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def listar_marcas_publicas(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:marcas:publicas"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("marcas").select("*").eq("estado", True).order("nombre").execute()
        
        if respuesta.data:
            await redis_client.setex(cache_key, 1800, json.dumps(respuesta.data))
            
        return respuesta.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def crear_marca(
    nombre: str = Form(...),
    descripcion: str = Form(None),
    imagen: UploadFile = File(None),
    usuario_id: str = Depends(verificar_permiso("marcas_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        url_imagen = None
        if imagen and imagen.filename:
            contenido = await imagen.read()
            url_imagen = subir_imagen(contenido)

        nueva_marca = {
            "nombre": nombre,
            "slug": generar_slug(nombre),
            "descripcion": descripcion,
            "imagen_marca": url_imagen
        }

        respuesta = supabase_admin.table("marcas").insert(nueva_marca).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nueva Marca Creada",
                mensaje=f"{autor} ha creado la marca '{nombre}'.",
                enlace="marcas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_marcas(redis_client)
        return respuesta.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{marca_id}")
async def actualizar_marca(
    marca_id: str,
    nombre: str = Form(...),
    descripcion: str = Form(None),
    imagen: UploadFile = File(None),
    usuario_id: str = Depends(verificar_permiso("marcas_edit")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        datos_actualizar = {
            "nombre": nombre,
            "slug": generar_slug(nombre),
            "descripcion": descripcion
        }

        if imagen and imagen.filename:
            contenido = await imagen.read()
            datos_actualizar["imagen_marca"] = subir_imagen(contenido)

        respuesta = supabase_admin.table("marcas").update(datos_actualizar).eq("id", marca_id).execute()
        
        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Marca no encontrada")

        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Marca Modificada",
                mensaje=f"{autor} ha modificado la marca '{nombre}'.",
                enlace="marcas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_marcas(redis_client)
        return respuesta.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{marca_id}/toggle-estado")
async def alternar_estado_marca(
    marca_id: str, 
    usuario_id: str = Depends(verificar_permiso("marcas_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        marca = supabase_admin.table("marcas").select("estado, nombre").eq("id", marca_id).single().execute()
        if not marca.data:
            raise HTTPException(status_code=404, detail="Marca no encontrada")
            
        nuevo_estado = not marca.data.get("estado", True)
        nombre_marca = marca.data.get("nombre", "Desconocida")
        
        supabase_admin.table("marcas").update({"estado": nuevo_estado}).eq("id", marca_id).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "publicada" if nuevo_estado else "ocultada"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Marca {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} la marca '{nombre_marca}'.",
                enlace="marcas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_marcas(redis_client)
        return {"mensaje": "Estado actualizado", "nuevo_estado": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
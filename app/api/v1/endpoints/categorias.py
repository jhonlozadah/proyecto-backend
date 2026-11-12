from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from app.api.dependencies import verificar_permiso
from app.services.cloud_storage import subir_imagen
from app.schemas.categoria_schema import CategoriaResponse
import re
from app.services.notificaciones_service import notificar_administradores
import json
from redis.asyncio import Redis
from app.core.database import supabase, supabase_admin, get_redis

router = APIRouter()

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

def generar_slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[\s_-]+', '-', texto)

@router.get("/", response_model=list[CategoriaResponse])
async def listar_categorias(
    usuario_id: str = Depends(verificar_permiso("categorias_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:categorias:todas"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        respuesta = supabase.table("categorias").select("*").order("nombre").execute()
        if respuesta.data:
            await redis_client.setex(cache_key, 900, json.dumps(respuesta.data))
        return respuesta.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/publicas", response_model=list[CategoriaResponse])
async def listar_categorias_publicas(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:categorias:publicas"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("categorias").select("*").eq("estado", True).order("nombre").execute()
        if respuesta.data:
            await redis_client.setex(cache_key, 3600, json.dumps(respuesta.data))
        return respuesta.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def crear_categoria(
    nombre: str = Form(...),
    descripcion: str = Form(None),
    imagen: UploadFile = File(None),
    usuario_id: str = Depends(verificar_permiso("categorias_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        slug = generar_slug(nombre)
        url_imagen = None
        
        if imagen and imagen.filename:
            contenido = await imagen.read()
            url_imagen = subir_imagen(contenido)

        nueva_categoria = {
            "nombre": nombre,
            "slug": slug,
            "descripcion": descripcion,
            "imagen_categoria": url_imagen
        }

        respuesta = supabase_admin.table("categorias").insert(nueva_categoria).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nueva Categoría Creada",
                mensaje=f"{autor} ha creado la categoría '{nombre}'.",
                enlace="categorias.html" 
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:categorias:todas", "cache:categorias:publicas")
        return respuesta.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{categoria_id}")
async def actualizar_categoria(
    categoria_id: str,
    nombre: str = Form(...),
    descripcion: str = Form(None),
    imagen: UploadFile = File(None),
    usuario_id: str = Depends(verificar_permiso("categorias_edit")),
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
            datos_actualizar["imagen_categoria"] = subir_imagen(contenido)

        respuesta = supabase_admin.table("categorias").update(datos_actualizar).eq("id", categoria_id).execute()
        
        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Categoría Modificada",
                mensaje=f"{autor} ha modificado la categoría '{nombre}'.",
                enlace="categorias.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
            
        await redis_client.delete("cache:categorias:todas", "cache:categorias:publicas")
        return respuesta.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{categoria_id}/toggle-estado")
async def alternar_estado(
    categoria_id: str, 
    usuario_id: str = Depends(verificar_permiso("categorias_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        cat = supabase_admin.table("categorias").select("estado, nombre").eq("id", categoria_id).single().execute()
        if not cat.data:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
            
        nuevo_estado = not cat.data.get("estado", True)
        nombre_cat = cat.data.get("nombre", "Desconocida")
        
        supabase_admin.table("categorias").update({"estado": nuevo_estado}).eq("id", categoria_id).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "publicada" if nuevo_estado else "ocultada"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Categoría {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} la categoría '{nombre_cat}'.",
                enlace="categorias.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        
        await redis_client.delete("cache:categorias:todas", "cache:categorias:publicas")
        return {"mensaje": "Estado actualizado exitosamente", "nuevo_estado": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
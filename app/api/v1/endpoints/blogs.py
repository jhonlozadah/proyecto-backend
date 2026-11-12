import re
import unicodedata
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from redis.asyncio import Redis
from app.core.database import supabase_admin, get_redis
import json
from app.api.dependencies import verificar_permiso
from app.services.cloud_storage import subir_imagen
from app.schemas.blog_schema import (
    BlogCreateRequest, 
    BlogUpdateRequest, 
    BlogResponse, 
    ComentarioCreateRequest, 
    ComentarioResponse
)
from app.services.notificaciones_service import notificar_administradores

router = APIRouter()

class ComentarioAnonimoCreateRequest(BaseModel):
    id_blog: UUID
    nombre: str
    correo: str
    comentario: str
    parent_id: Optional[UUID] = None

def generar_slug(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^\w\s-]', '', texto).lower()
    return re.sub(r'[-\s]+', '-', texto).strip('-')

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

def obtener_usuario_opcional(request: Request):
    """
    Extrae el ID de usuario si existe una sesión/token activa, de lo contrario retorna None.
    """
    try:
        token = request.cookies.get("access_token")
        if not token:
            auth = request.headers.get("Authorization")
            if auth and auth.startswith("Bearer "):
                token = auth.split(" ")[1]
        
        if token:
            user_res = supabase_admin.auth.get_user(token)
            if user_res and user_res.user:
                return {"id": user_res.user.id}
        return None
    except Exception:
        return None

@router.post("/upload-imagen")
async def subir_imagen_blog(
    file: UploadFile = File(...),
    usuario_id: str = Depends(verificar_permiso("blogs_create"))
):
    try:
        contenido = await file.read()
        url_cloudinary = subir_imagen(contenido)
        return {"url": url_cloudinary}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al subir imagen: {str(e)}")


@router.get("/publico", response_model=List[BlogResponse])
async def listar_blogs_publicos(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:blogs:publicos"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("blogs") \
            .select("*, categorias(nombre), usuarios(nombres, apellidos)") \
            .eq("estado", True) \
            .order("creado_en", desc=True) \
            .execute()
        
        if res.data:
            await redis_client.setex(cache_key, 3600, json.dumps(res.data))
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener blogs: {str(e)}")


@router.get("/", response_model=List[BlogResponse])
async def listar_blogs(
    usuario_id: str = Depends(verificar_permiso("blogs_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:blogs:admin_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("blogs").select("*, categorias(nombre)").order("creado_en", desc=True).execute()
        if res.data:
            await redis_client.setex(cache_key, 900, json.dumps(res.data))
        return res.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener blogs: {str(e)}")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def crear_blog(
    datos: BlogCreateRequest,
    usuario_id: str = Depends(verificar_permiso("blogs_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        slug = generar_slug(datos.titulo)
        nuevo_blog = {
            "id_usuario": usuario_id,
            "id_categoria": str(datos.id_categoria),
            "titulo": datos.titulo,
            "slug": slug,
            "subtitulo": datos.subtitulo,
            "primer_descripcion": datos.primer_descripcion,
            "segunda_descripcion": datos.segunda_descripcion,
            "imagen_principal": datos.imagen_principal,
            "imagen_banner": datos.imagen_banner,
            "imagen_producto_1": datos.imagen_producto_1,
            "imagen_producto_2": datos.imagen_producto_2,
            "estado": True
        }

        res = supabase_admin.table("blogs").insert(nuevo_blog).execute()

        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nuevo Blog Publicado",
                mensaje=f"{autor} ha creado un nuevo artículo titulado '{datos.titulo}'.",
                enlace="blog.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:blogs:publicos", "cache:blogs:admin_lista")
        return {"mensaje": "Blog creado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear blog: {str(e)}")


@router.put("/{blog_id}")
async def actualizar_blog(
    blog_id: str,
    datos: BlogUpdateRequest,
    usuario_id: str = Depends(verificar_permiso("blogs_edit")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        update_data = {k: v for k, v in datos.dict().items() if v is not None}
        if "id_categoria" in update_data:
            update_data["id_categoria"] = str(update_data["id_categoria"])
        if "titulo" in update_data:
            update_data["slug"] = generar_slug(update_data["titulo"])

        res = supabase_admin.table("blogs").update(update_data).eq("id", blog_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Blog no encontrado")

        try:
            autor = obtener_nombre_usuario(usuario_id)
            titulo_blog = update_data.get("titulo", res.data[0].get("titulo", "un artículo"))
            notificar_administradores(
                tipo="sistema",
                titulo="Blog Modificado",
                mensaje=f"{autor} ha editado el artículo '{titulo_blog}'.",
                enlace="blog.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        slug_actualizado = res.data[0].get("slug")
        await redis_client.delete("cache:blogs:publicos", "cache:blogs:admin_lista", f"cache:blogs:slug:{slug_actualizado}")
        return {"mensaje": "Blog actualizado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar blog: {str(e)}")


@router.put("/toggle-estado/{blog_id}")
async def alternar_estado_blog(
    blog_id: str,
    usuario_id: str = Depends(verificar_permiso("blogs_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        blog = supabase_admin.table("blogs").select("estado, titulo").eq("id", blog_id).single().execute()
        if not blog.data:
            raise HTTPException(status_code=404, detail="Blog no encontrado")

        nuevo_estado = not blog.data.get("estado", True)
        res = supabase_admin.table("blogs").update({"estado": nuevo_estado}).eq("id", blog_id).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "publicado" if nuevo_estado else "ocultado"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Artículo {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} el artículo '{blog.data.get('titulo')}'.",
                enlace="blog.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        slug = res.data[0].get("slug") if res.data else None
        claves_a_borrar = ["cache:blogs:publicos", "cache:blogs:admin_lista"]
        if slug: claves_a_borrar.append(f"cache:blogs:slug:{slug}")
        await redis_client.delete(*claves_a_borrar)
        return {"mensaje": "Estado del blog actualizado", "nuevo_estado": nuevo_estado}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al cambiar estado del blog: {str(e)}")


@router.get("/slug/{slug}")
async def obtener_blog_por_slug(slug: str, redis_client: Redis = Depends(get_redis)):
    cache_key = f"cache:blogs:slug:{slug}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("blogs") \
            .select("*, categorias(nombre), usuarios(nombres, apellidos, imagen_perfil)") \
            .eq("slug", slug) \
            .eq("estado", True) \
            .limit(1) \
            .execute()
        
        if not res.data or len(res.data) == 0:
            raise HTTPException(status_code=404, detail="El artículo no existe o fue desactivado.")
            
        await redis_client.setex(cache_key, 3600, json.dumps(res.data[0]))
        return res.data[0]
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar el artículo: {str(e)}")

@router.get("/{blog_id}/comentarios", response_model=List[ComentarioResponse])
async def listar_comentarios_blog(blog_id: str, redis_client: Redis = Depends(get_redis)):
    cache_key = f"cache:blogs:comentarios:{blog_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("comentario_blogs") \
            .select("*, usuarios(nombres, apellidos, correo, imagen_perfil)") \
            .eq("id_blog", blog_id) \
            .eq("estado", True) \
            .order("fecha_hora", desc=False) \
            .execute()
            
        if res.data:
            await redis_client.setex(cache_key, 900, json.dumps(res.data))
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener comentarios: {str(e)}")

@router.post("/comentarios", status_code=status.HTTP_201_CREATED)
async def crear_comentario_blog(
    datos: ComentarioAnonimoCreateRequest,
    usuario_sesion = Depends(obtener_usuario_opcional),
    redis_client: Redis = Depends(get_redis)
):
    try:
        id_usuario_real = usuario_sesion["id"] if (usuario_sesion and isinstance(usuario_sesion, dict) and "id" in usuario_sesion) else None

        comentario_final = datos.comentario.strip()
        if not id_usuario_real:
            comentario_final = f"[{datos.nombre.strip()} - {datos.correo.strip()}]\n{datos.comentario.strip()}"

        nuevo_comentario = {
            "id_usuario": id_usuario_real,
            "id_blog": str(datos.id_blog),
            "parent_id": str(datos.parent_id) if datos.parent_id else None,
            "comentario": comentario_final,
            "estado": False 
        }
        
        res = supabase_admin.table("comentario_blogs").insert(nuevo_comentario).execute()
        
        try:
            notificar_administradores(
                tipo="consulta",
                titulo="Nuevo Comentario en Moderación",
                mensaje=f"Se ha recibido un nuevo comentario de {datos.nombre.strip()} en un artículo. Requiere aprobación.",
                enlace="comentarios.html" 
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:comentarios_todos")
        return {"mensaje": "Comentario enviado a moderación", "data": res.data[0]}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al publicar comentario: {str(e)}")

@router.get("/admin/comentarios/todos")
async def listar_comentarios_admin(
    usuario_id: str = Depends(verificar_permiso("comentarios_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:comentarios_todos"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("comentario_blogs") \
            .select("*, blogs(titulo, id_categoria, categorias(nombre)), usuarios(nombres, apellidos, correo)") \
            .order("fecha_hora", desc=True) \
            .execute()
            
        if res.data:
            await redis_client.setex(cache_key, 300, json.dumps(res.data))
        return res.data or []
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar comentarios: {str(e)}")
    
@router.put("/admin/comentarios/{comentario_id}/estado")
async def moderar_comentario_admin(
    comentario_id: str,
    accion: str,
    usuario_id: str = Depends(verificar_permiso("comentarios_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        accion_lower = accion.lower().strip()
        
        if accion_lower == "approve":
            nuevo_estado = True
        elif accion_lower in ["pending", "reject"]:
            nuevo_estado = False
        else:
            raise HTTPException(status_code=400, detail="Acción no válida. Use 'approve', 'pending' o 'reject'.")

        res = supabase_admin.table("comentario_blogs") \
            .update({"estado": nuevo_estado}) \
            .eq("id", comentario_id) \
            .execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Comentario no encontrado")
            
        id_blog_afectado = res.data[0].get("id_blog")
        await redis_client.delete("cache:admin:comentarios_todos", f"cache:blogs:comentarios:{id_blog_afectado}")

        return {"mensaje": "Estado de comentario actualizado", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al moderar comentario: {str(e)}")
import json
import re
from fastapi import APIRouter, Depends, HTTPException, File, status, UploadFile, Form, Query
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.producto_schema import ProductoResponse
from app.services.notificaciones_service import notificar_administradores
from redis.asyncio import Redis
from app.core.database import supabase, supabase_admin, get_redis
from app.api.dependencies import verificar_permiso, obtener_usuario_actual, rate_limiter
from app.services.cloud_storage import subir_imagen

router = APIRouter()

class ResenaCreate(BaseModel):
    valoracion: int
    comentario: str

class EstadoResenaUpdate(BaseModel):
    estado: bool

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data['nombres']} {res.data['apellidos']}".strip()
    except:
        pass
    return "Un administrador"

def generar_slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[\s_-]+', '-', texto)

async def limpiar_cache_productos(redis_client: Redis, producto_id: Optional[str] = None):
    claves = [
        "cache:productos:top_ventas",
        "cache:productos:recientes",
        "cache:admin:productos_lista",
        "cache:admin:resenas_lista"
    ]
    for key in claves:
        await redis_client.delete(key)
        
    keys_patron = await redis_client.keys("cache:productos:*")
    for key in keys_patron:
        await redis_client.delete(key)

@router.get("/top-ventas", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def get_top_ventas(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:productos:top_ventas"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        response = supabase_admin.rpc('obtener_top_ventas', {'limite': 10}).execute()
        data = response.data or []
        if data:
            await redis_client.setex(cache_key, 1800, json.dumps(data))
        return data
    except Exception as e:
        print(f"Error al obtener top ventas: {e}")
        return []

@router.get("/buscar-publico", dependencies=[Depends(rate_limiter(max_requests=40, window_seconds=60))])
async def buscar_productos_publico(
    q: Optional[str] = Query(None, description="Término de búsqueda"),
    categoria_id: Optional[str] = Query(None, description="Filtrar por ID de categoría"),
    orden: Optional[str] = Query("03", description="01: Menor-Mayor, 02: Mayor-Menor, 03: Recientes"),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:buscar:{q or 'all'}:{categoria_id or 'all'}:{orden}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        query = supabase_admin.table("productos").select("*, categorias(nombre)").eq("estado", True)
        if q and q.strip():
            busqueda_limpia = re.sub(r'[^\w\s]', ' ', q)
            palabras_clave = [p.strip() for p in busqueda_limpia.split() if len(p.strip()) > 1]
            for palabra in palabras_clave:
                query = query.ilike("nombre", f"%{palabra}%")

        if categoria_id and categoria_id.strip():
            query = query.eq("id_categoria", categoria_id)
        if orden == "01":
            query = query.order("precio_normal", desc=False)
        elif orden == "02":
            query = query.order("precio_normal", desc=True)
        else:
            query = query.order("creado_en", desc=True)
        res = query.execute()
        data = res.data or []
        if data:
            await redis_client.setex(cache_key, 600, json.dumps(data))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda: {str(e)}")

@router.get("/recientes", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_productos_recientes(redis_client: Redis = Depends(get_redis)):
    cache_key = "cache:productos:recientes"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        respuesta = supabase.table("productos").select(
            "id, nombre, slug, precio_normal, precio_oferta, porcentaje_descuento, stock, imagen_principal"
        ).order("creado_en", desc=True).limit(15).execute()

        data = respuesta.data or []
        if data:
            await redis_client.setex(cache_key, 900, json.dumps(data))
        return data
    except Exception as e:
        print(f"Error al obtener recientes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[ProductoResponse])
async def listar_productos_admin(
    usuario = Depends(verificar_permiso("productos_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:productos_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("productos").select("*, categorias(nombre), marcas(nombre)").order("creado_en", desc=True).execute()
        data = respuesta.data or []
        if data:
            await redis_client.setex(cache_key, 900, json.dumps(data))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ProductoResponse)
async def crear_producto(
    usuario = Depends(verificar_permiso("productos_create")),
    nombre: str = Form(...),
    id_categoria: str = Form(...),
    id_marca: str = Form(...),
    sku: str = Form(...),
    descripcion_corta: str = Form(...),
    descripcion_detallada: str = Form(None),
    precio_normal: float = Form(...),
    precio_oferta: float = Form(None),
    cantidad: str = Form(...),
    presentacion: str = Form(...),
    stock: int = Form(...),
    vida_util: str = Form(None),
    base_quimica: str = Form(None),
    aspecto: str = Form(None),
    densidad: str = Form(None),
    disolventes: str = Form(None),
    etiquetas: str = Form(...),
    url_ficha_tecnica: str = Form(None),
    destacado: bool = Form(False),
    mainImageIndex: int = Form(0),
    imagenes: List[UploadFile] = File(...),
    redis_client: Redis = Depends(get_redis)
):
    try:
        porcentaje = 0
        if precio_oferta and precio_oferta < precio_normal:
            porcentaje = round(((precio_normal - precio_oferta) / precio_normal) * 100, 2)

        urls_imagenes = []
        for img in imagenes[:5]:
            contenido = await img.read()
            urls_imagenes.append(subir_imagen(contenido))

        if not urls_imagenes:
            raise ValueError("Se requiere al menos una imagen")

        imagen_principal_url = urls_imagenes[mainImageIndex] if mainImageIndex < len(urls_imagenes) else urls_imagenes[0]
        nuevo_producto = {
            "nombre": nombre,
            "slug": generar_slug(nombre),
            "id_categoria": id_categoria,
            "id_marca": id_marca,
            "sku": sku,
            "descripcion_corta": descripcion_corta,
            "descripcion_detallada": descripcion_detallada,
            "precio_normal": precio_normal,
            "precio_oferta": precio_oferta,
            "porcentaje_descuento": porcentaje,
            "cantidad": cantidad, 
            "presentacion": presentacion,
            "stock": stock,
            "vida_util": vida_util,
            "base_quimica": base_quimica,
            "aspecto": aspecto,
            "densidad": densidad,
            "disolventes": disolventes,
            "etiquetas": etiquetas,
            "url_ficha_tecnica": url_ficha_tecnica,
            "destacado": destacado,
            "imagen_principal": imagen_principal_url
        }

        prod_res = supabase_admin.table("productos").insert(nuevo_producto).execute()
        producto_id = prod_res.data[0]["id"]
        galeria_data = [{"id_producto": producto_id, "url_imagen": url, "orden": i} for i, url in enumerate(urls_imagenes)]
        supabase_admin.table("producto_imagenes").insert(galeria_data).execute()
        try:
            autor = obtener_nombre_usuario(usuario)
            notificar_administradores(
                tipo="sistema",
                titulo="Nuevo Producto Creado",
                mensaje=f"{autor} ha registrado el producto '{nombre}'.",
                enlace=f"editar-producto.html?id={producto_id}"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_productos(redis_client)
        completo = supabase_admin.table("productos").select("*, categorias(nombre), marcas(nombre)").eq("id", producto_id).single().execute()
        return completo.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/toggle-estado/{producto_id}")
async def alternar_estado_producto(producto_id: str, usuario = Depends(verificar_permiso("productos_delete")), redis_client: Redis = Depends(get_redis)):
    try:
        prod = supabase_admin.table("productos").select("estado, nombre").eq("id", producto_id).single().execute()
        if not prod.data:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
            
        nuevo_estado = not prod.data.get("estado", True)
        nombre_prod = prod.data.get("nombre", "Desconocido")
        
        supabase_admin.table("productos").update({"estado": nuevo_estado}).eq("id", producto_id).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario)
            accion = "publicado" if nuevo_estado else "ocultado"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Producto {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} el producto '{nombre_prod}'.",
                enlace=f"editar-producto.html?id={producto_id}"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_productos(redis_client, producto_id)
        return {"mensaje": "Estado actualizado", "nuevo_estado": nuevo_estado}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{producto_id}", response_model=ProductoResponse)
async def actualizar_producto(
    producto_id: str,
    usuario: str = Depends(verificar_permiso("productos_edit")),
    nombre: str = Form(...),
    id_categoria: str = Form(...),
    id_marca: str = Form(...),
    descripcion_corta: str = Form(...),
    descripcion_detallada: str = Form(None),
    precio_normal: float = Form(...),
    precio_oferta: float = Form(None),
    cantidad: str = Form(...),
    presentacion: str = Form(...),
    stock: int = Form(...),
    vida_util: str = Form(None),
    base_quimica: str = Form(None),
    aspecto: str = Form(None),
    densidad: str = Form(None),
    disolventes: str = Form(None),
    etiquetas: str = Form(...),
    url_ficha_tecnica: str = Form(None),
    destacado: bool = Form(False),
    mainImageIndex: int = Form(0),
    imagenes: Optional[List[UploadFile]] = File(None),
    redis_client: Redis = Depends(get_redis)
):
    try:
        porcentaje = 0
        if precio_oferta and precio_oferta < precio_normal:
            porcentaje = round(((precio_normal - precio_oferta) / precio_normal) * 100, 2)

        datos_actualizar = {
            "nombre": nombre,
            "id_categoria": id_categoria,
            "id_marca": id_marca,
            "descripcion_corta": descripcion_corta,
            "descripcion_detallada": descripcion_detallada,
            "precio_normal": precio_normal,
            "precio_oferta": precio_oferta,
            "porcentaje_descuento": porcentaje,
            "cantidad": str(cantidad),
            "presentacion": presentacion,
            "stock": stock,
            "vida_util": vida_util,
            "base_quimica": base_quimica,
            "aspecto": aspecto,
            "densidad": densidad,
            "disolventes": disolventes,
            "etiquetas": etiquetas,
            "url_ficha_tecnica": url_ficha_tecnica,
            "destacado": destacado
        }

        if imagenes and len(imagenes) > 0 and imagenes[0].filename:
            urls_imagenes = []
            for img in imagenes[:5]:
                contenido = await img.read()
                urls_imagenes.append(subir_imagen(contenido))
            if urls_imagenes:
                imagen_principal_url = urls_imagenes[mainImageIndex] if mainImageIndex < len(urls_imagenes) else urls_imagenes[0]
                datos_actualizar["imagen_principal"] = imagen_principal_url
                supabase_admin.table("producto_imagenes").delete().eq("id_producto", producto_id).execute()
                galeria_data = [{"id_producto": producto_id, "url_imagen": url, "orden": i} for i, url in enumerate(urls_imagenes)]
                supabase_admin.table("producto_imagenes").insert(galeria_data).execute()

        respuesta = supabase_admin.table("productos").update(datos_actualizar).eq("id", producto_id).execute()
        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        try:
            autor = obtener_nombre_usuario(usuario)
            notificar_administradores(
                tipo="sistema",
                titulo="Producto Modificado",
                mensaje=f"{autor} ha editado el producto '{nombre}'.",
                enlace=f"editar-producto.html?id={producto_id}"
            )
            
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_productos(redis_client, producto_id)
        completo = supabase_admin.table("productos").select("*, categorias(nombre), marcas(nombre)").eq("id", producto_id).single().execute()
        return completo.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{producto_id}", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_producto_por_id(
    producto_id: str, 
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:id:{producto_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("productos").select(
            "*, categorias(nombre), marcas(*), producto_imagenes(url_imagen)"
        ).eq("id", producto_id).single().execute()

        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        await redis_client.setex(cache_key, 1800, json.dumps(respuesta.data))
        return respuesta.data
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error al obtener detalles del producto: {e}")
        raise HTTPException(status_code=500, detail="Error interno al buscar el producto")

@router.get("/slug/{slug}", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_producto_por_slug(
    slug: str, 
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:slug:{slug}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        respuesta = supabase.table("productos").select(
            "*, categorias(nombre), marcas(*), producto_imagenes(url_imagen)"
        ).eq("slug", slug).single().execute()

        if not respuesta.data:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
            
        await redis_client.setex(cache_key, 1800, json.dumps(respuesta.data))
        return respuesta.data
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error al obtener producto por slug: {e}")
        raise HTTPException(status_code=500, detail="Error interno al buscar el producto")

@router.get("/relacionados/{id_categoria}/{id_producto}", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_productos_relacionados(
    id_categoria: str, 
    id_producto: str, 
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:relacionados:{id_categoria}:{id_producto}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        respuesta = supabase.table("productos").select(
            "id, nombre, slug, precio_normal, precio_oferta, porcentaje_descuento, stock, imagen_principal"
        ).eq("id_categoria", id_categoria).eq("estado", True).neq("id", id_producto).limit(8).execute()

        data = respuesta.data or []
        if data:
            await redis_client.setex(cache_key, 1800, json.dumps(data))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error al buscar productos relacionados")

@router.get("/categoria/{slug_categoria}", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_productos_por_categoria(
    slug_categoria: str, 
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:categoria:{slug_categoria}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        categoria_resp = supabase.table("categorias").select("id, nombre").eq("slug", slug_categoria).single().execute()
        if not categoria_resp.data:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        id_categoria = categoria_resp.data["id"]
        productos_resp = supabase.table("productos").select(
            "id, nombre, slug, precio_normal, precio_oferta, porcentaje_descuento, stock, imagen_principal"
        ).eq("id_categoria", id_categoria).eq("estado", True).execute()

        resultado = {
            "categoria_nombre": categoria_resp.data["nombre"],
            "productos": productos_resp.data or []
        }
        await redis_client.setex(cache_key, 1800, json.dumps(resultado))
        return resultado
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno al buscar productos por categoría")
    
@router.get("/{id_producto}/resenas", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_resenas(
    id_producto: str, 
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:productos:resenas:{id_producto}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        response = supabase_admin.table("comentario_producto") \
            .select("*, usuarios(nombres, apellidos, imagen_perfil)") \
            .eq("id_producto", id_producto) \
            .eq("estado", True) \
            .order("fecha_hora", desc=True) \
            .execute()

        resenas_formateadas = []
        for r in (response.data or []):
            nombre = r.get("usuarios", {}).get("nombres", "") if r.get("usuarios") else ""
            apellido = r.get("usuarios", {}).get("apellidos", "") if r.get("usuarios") else ""
            nombre_completo = f"{nombre} {apellido}".strip()
            imagen = r.get("usuarios", {}).get("imagen_perfil", "") if r.get("usuarios") else ""
            fecha_str = r['fecha_hora'].split('T')[0] if r.get('fecha_hora') else "Reciente"
            
            resenas_formateadas.append({
                "id": r["id"],
                "valoracion": r["valoracion"],
                "comentario": r["comentario"],
                "fecha": fecha_str,
                "usuario_nombre": nombre_completo if nombre_completo else "Cliente Verificado",
                "usuario_imagen": imagen 
            })
            
        await redis_client.setex(cache_key, 900, json.dumps(resenas_formateadas))
        return resenas_formateadas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{id_producto}/resenas", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
async def crear_resena(
    id_producto: str, 
    resena: ResenaCreate, 
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    try:
        existente = supabase_admin.table("comentario_producto") \
            .select("id") \
            .eq("id_producto", id_producto) \
            .eq("id_usuario", usuario_id) \
            .execute()
            
        if len(existente.data or []) > 0:
            raise HTTPException(status_code=400, detail="Ya has publicado una reseña para este producto.")

        nueva_resena = {
            "id_producto": id_producto,
            "id_usuario": usuario_id,
            "valoracion": resena.valoracion,
            "comentario": resena.comentario,
            "estado": False 
        }
        
        supabase_admin.table("comentario_producto").insert(nueva_resena).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="consulta",
                titulo="Nueva Reseña de Producto",
                mensaje=f"El cliente {autor} ha dejado una reseña de {resena.valoracion} estrellas. Requiere moderación.",
                enlace="resenas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
            
        await limpiar_cache_productos(redis_client, id_producto)
        return {"mensaje": "Reseña enviada y pendiente de aprobación"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error al guardar reseña: {e}")
        raise HTTPException(status_code=500, detail="Error al guardar la reseña en la base de datos.")
    
@router.get("/admin/resenas-todas")
async def listar_resenas_admin(
    usuario_id: str = Depends(verificar_permiso("resenas_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:resenas_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        response = supabase_admin.table("comentario_producto") \
            .select("*, usuarios(nombres, apellidos, correo), productos(nombre, sku)") \
            .order("fecha_hora", desc=True) \
            .execute()
            
        data = response.data or []
        if data:
            await redis_client.setex(cache_key, 900, json.dumps(data))
        return data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/admin/resenas/{id_resena}/estado")
async def cambiar_estado_resena(
    id_resena: str, 
    datos: EstadoResenaUpdate,
    usuario_id: str = Depends(verificar_permiso("resenas_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        res = supabase_admin.table("comentario_producto").update({"estado": datos.estado}).eq("id", id_resena).select("id_producto").execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Reseña no encontrada")
        producto_id = res.data[0]["id_producto"]
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "aprobado" if datos.estado else "ocultado"
            notificar_administradores(
                tipo="sistema",
                titulo="Reseña Moderada",
                mensaje=f"{autor} ha {accion} una reseña de producto.",
                enlace="resenas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        await limpiar_cache_productos(redis_client, producto_id)
        return {"mensaje": "Estado de la reseña actualizado"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin/resenas/{id_resena}")
async def eliminar_resena(
    id_resena: str, 
    usuario_id: str = Depends(verificar_permiso("resenas_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        resena_db = supabase_admin.table("comentario_producto").select("id_producto").eq("id", id_resena).execute()
        supabase_admin.table("comentario_producto").delete().eq("id", id_resena).execute()
        if resena_db.data:
            await limpiar_cache_productos(redis_client, resena_db.data[0]["id_producto"])
            
        return {"mensaje": "Reseña eliminada permanentemente"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
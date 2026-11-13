import requests
import traceback
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Cookie, Response
from pydantic import BaseModel, EmailStr
from app.schemas.usuario_schema import UsuarioPerfilResponse, UsuarioUpdate, UsuarioPasswordUpdate, CrearUsuarioAdminRequest, UsuarioAdminResponse
from app.core.database import supabase, supabase_admin, get_redis
from app.api.dependencies import obtener_usuario_actual, verificar_permiso, rate_limiter
from app.services.cloud_storage import subir_imagen
from app.core.config import settings
from typing import List
from app.services.notificaciones_service import notificar_administradores
import json
from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis

router = APIRouter()

class MFADesactivarRequest(BaseModel):
    codigo: str

class MFAActivarRequest(BaseModel):
    factor_id: str
    codigo: str

class EditarUsuarioAdminRequest(BaseModel):
    nombres: str
    apellidos: str
    correo: EmailStr
    rol: str

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data['nombres']} {res.data['apellidos']}".strip()
    except:
        pass
    return "Un administrador"

async def limpiar_cache_usuario(redis_client: Redis, target_usuario_id: str = None):
    await redis_client.delete("cache:admin:usuarios_lista")
    if target_usuario_id:
        await redis_client.delete(f"cache:usuario:perfil:{target_usuario_id}")

async def limpiar_cache_deseos(redis_client: Redis, usuario_id: str):
    await redis_client.delete(f"cache:usuario:deseos:{usuario_id}")

@router.get("/perfil", dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def obtener_perfil(
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:usuario:perfil:{usuario_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    res = supabase_admin.table("usuarios").select("*, roles(nombre, permisos)").eq("id", usuario_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario = res.data
    permisos = usuario.get("roles", {}).get("permisos", {}) if usuario.get("roles") else {}

    perfil = {
        "id": usuario.get("id"),
        "nombres": usuario.get("nombres", ""),
        "apellidos": usuario.get("apellidos", ""),
        "correo": usuario.get("correo", ""),
        "telefono": usuario.get("telefono", ""),
        "tipo_documento": usuario.get("tipo_documento", ""),
        "numero_documento": usuario.get("numero_documento", ""),
        "razon_social": usuario.get("razon_social", ""),
        "direccion": usuario.get("direccion", ""),
        "referencia": usuario.get("referencia", ""),
        "departamento": usuario.get("departamento", ""),
        "provincia": usuario.get("provincia", ""),
        "distrito": usuario.get("distrito", ""),
        "mfa_activo": usuario.get("mfa_activo", False),
        "imagen_perfil": usuario.get("imagen_perfil", ""),
        "rol": usuario.get("roles", {}).get("nombre", "cliente"),
        "permisos": permisos
    }
    
    await redis_client.setex(cache_key, 600, json.dumps(perfil))
    return perfil

@router.put("/perfil")
async def actualizar_perfil(
    datos: UsuarioUpdate, 
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    datos_dict = datos.model_dump(exclude_unset=True)
    supabase.table("usuarios").update(datos_dict).eq("id", usuario_id).execute()
    await limpiar_cache_usuario(redis_client, usuario_id)
    return {"mensaje": "Perfil actualizado correctamente"}

@router.post("/perfil/imagen")
async def actualizar_foto(
    imagen: UploadFile = File(...), 
    usuario_id: str = Depends(obtener_usuario_actual),
    access_token: str = Cookie(None),
    redis_client: Redis = Depends(get_redis)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Sesión no encontrada o expirada.")

    contenido = await imagen.read()
    url_imagen = subir_imagen(contenido)
    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation" 
    }

    url_db = f"{settings.SUPABASE_URL}/rest/v1/usuarios?id=eq.{usuario_id}"
    res_db = requests.patch(url_db, headers=headers, json={"imagen_perfil": url_imagen})
    if res_db.status_code >= 400 or not res_db.json():
        raise HTTPException(
            status_code=400, 
            detail="La imagen subió, pero la base de datos bloqueó el guardado por permisos."
        )

    await limpiar_cache_usuario(redis_client, usuario_id)
    return {"mensaje": "Foto actualizada", "url": url_imagen}

@router.put("/password", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
def actualizar_password(datos: UsuarioPasswordUpdate, usuario_id: str = Depends(obtener_usuario_actual)):
    usuario_db = supabase.table("usuarios").select("correo").eq("id", usuario_id).single().execute()
    if not usuario_db.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    correo = usuario_db.data["correo"]

    try:
        supabase.auth.sign_in_with_password({
            "email": correo,
            "password": datos.contrasena_actual
        })

        supabase.auth.update_user({"password": datos.nueva_contrasena})
        return {"mensaje": "Contraseña actualizada correctamente"}

    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail="La contraseña actual es incorrecta o hubo un error al actualizar."
        )

@router.post("/mfa/generar", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
def generar_mfa(
    usuario_id: str = Depends(obtener_usuario_actual),
    access_token: str = Cookie(None)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Sesión no encontrada.")

    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        url_user = f"{settings.SUPABASE_URL}/auth/v1/user"
        res_user = requests.get(url_user, headers=headers)
        if res_user.status_code == 200:
            user_data = res_user.json()
            factores = user_data.get("factors", [])
            for factor in factores:
                if factor.get("factor_type") == "totp":
                    if factor.get("status") == "verified":
                        raise HTTPException(
                            status_code=400, 
                            detail="El MFA ya está verificado y activo para esta cuenta."
                        )
                    else:
                        factor_id_viejo = factor.get("id")
                        url_delete = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id_viejo}"
                        requests.delete(url_delete, headers=headers)

        url_factors = f"{settings.SUPABASE_URL}/auth/v1/factors"
        res = requests.post(url_factors, headers=headers, json={
            "factor_type": "totp", 
            "friendly_name": "Edificando E-commerce"
        })

        if res.status_code >= 400:
            error_data = res.json()
            error_msg = error_data.get("msg") or error_data.get("message") or res.text
            raise HTTPException(status_code=400, detail=error_msg)

        data = res.json()
        return {
            "factor_id": data["id"],
            "qr_code": data["totp"]["qr_code"], 
            "secret": data["totp"]["secret"]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mfa/activar", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
async def activar_mfa(
    datos: MFAActivarRequest, 
    response: Response,
    usuario_id: str = Depends(obtener_usuario_actual),
    access_token: str = Cookie(None),
    redis_client: Redis = Depends(get_redis)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Sesión no encontrada.")

    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        url_challenge = f"{settings.SUPABASE_URL}/auth/v1/factors/{datos.factor_id}/challenge"
        res_challenge = requests.post(url_challenge, headers=headers)
        if res_challenge.status_code >= 400:
            raise ValueError("Error al crear desafío de seguridad")

        challenge_id = res_challenge.json()["id"]
        url_verify = f"{settings.SUPABASE_URL}/auth/v1/factors/{datos.factor_id}/verify"
        res_verify = requests.post(url_verify, headers=headers, json={
            "challenge_id": challenge_id, 
            "code": datos.codigo
        })
        
        if res_verify.status_code >= 400:
            raise ValueError("Código MFA incorrecto o expirado")

        verify_data = res_verify.json()
        nuevo_token = verify_data.get("access_token")

        url_db = f"{settings.SUPABASE_URL}/rest/v1/usuarios?id=eq.{usuario_id}"
        res_db = requests.patch(url_db, headers=headers, json={"mfa_activo": True})
        if res_db.status_code >= 400:
            print(f"[ERROR BD] Fallo RLS: {res_db.text}")
            raise ValueError("MFA se activó en seguridad, pero la base de datos rechazó el guardado.")

        if nuevo_token:
            response.set_cookie(
                key="access_token",
                value=nuevo_token,
                httponly=True,
                secure=True, # Cambiar a True si usas HTTPS en producción
                samesite="none",
                path="/",
                max_age=3600
            )

        await limpiar_cache_usuario(redis_client, usuario_id)
        return {"mensaje": "MFA activado con éxito"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/mfa/desactivar", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
async def desactivar_mfa(
    datos: MFADesactivarRequest,
    usuario_id: str = Depends(obtener_usuario_actual),
    access_token: str = Cookie(None),
    redis_client: Redis = Depends(get_redis)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Sesión no encontrada.")

    headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        url_user = f"{settings.SUPABASE_URL}/auth/v1/user"
        res_user = requests.get(url_user, headers=headers)
        if res_user.status_code >= 400:
            raise ValueError("No se pudieron cargar los datos de seguridad del usuario.")

        user_data = res_user.json()
        factores = user_data.get("factors", [])
        factor_totp = next((f for f in factores if f["factor_type"] == "totp" and f["status"] == "verified"), None)
        if not factor_totp:
            raise ValueError("No tienes un MFA activo para desactivar.")
            
        factor_id = factor_totp["id"]
        url_challenge = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id}/challenge"
        res_challenge = requests.post(url_challenge, headers=headers)
        if res_challenge.status_code >= 400:
            raise ValueError("Error al crear desafío de validación.")
            
        challenge_id = res_challenge.json()["id"]
        url_verify = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id}/verify"
        res_verify = requests.post(url_verify, headers=headers, json={
            "challenge_id": challenge_id, 
            "code": datos.codigo
        })
        
        if res_verify.status_code >= 400:
            raise ValueError("El código de seguridad es incorrecto.")

        url_delete = f"{settings.SUPABASE_URL}/auth/v1/factors/{factor_id}"
        res_delete = requests.delete(url_delete, headers=headers)
        if res_delete.status_code >= 400:
            raise ValueError("No se pudo desvincular el dispositivo de Supabase.")

        url_db = f"{settings.SUPABASE_URL}/rest/v1/usuarios?id=eq.{usuario_id}"
        res_db = requests.patch(url_db, headers=headers, json={"mfa_activo": False})
        if res_db.status_code >= 400:
            print(f"[ERROR BD] Fallo RLS: {res_db.text}")
            raise ValueError("MFA se desactivó en seguridad, pero la base de datos rechazó el guardado.")

        await limpiar_cache_usuario(redis_client, usuario_id)
        return {"mensaje": "MFA desactivado con éxito"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pedidos")
def obtener_pedidos_recientes(usuario_id: str = Depends(obtener_usuario_actual)):
    try:
        respuesta = supabase.table("pedidos") \
            .select("id, total, estado, fecha_hora_pedido") \
            .eq("id_cliente", usuario_id) \
            .order("fecha_hora_pedido", desc=True) \
            .limit(5) \
            .execute()

        pedidos_formateados = []
        for p in respuesta.data:
            fecha_corta = p["fecha_hora_pedido"].split("T")[0] 
            pedidos_formateados.append({
                "id": p["id"],
                "fecha": fecha_corta,
                "total": p["total"],
                "estado": p["estado"].capitalize(),
                "cantidad_productos": 1 
            })
            
        return pedidos_formateados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos: {str(e)}")

@router.get("/historial-pedidos")
def obtener_historial_completo(usuario_id: str = Depends(obtener_usuario_actual)):
    try:
        respuesta = supabase.table("pedidos") \
            .select("id, total, estado, fecha_hora_pedido") \
            .eq("id_cliente", usuario_id) \
            .order("fecha_hora_pedido", desc=True) \
            .execute()
            
        pedidos_formateados = []
        for p in respuesta.data:
            fecha_corta = p["fecha_hora_pedido"].split("T")[0] 
            pedidos_formateados.append({
                "id": p["id"],
                "fecha": fecha_corta,
                "total": p["total"],
                "estado": p["estado"].capitalize(),
                "cantidad_productos": 1
            })
        return pedidos_formateados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el historial completo: {str(e)}")

@router.get("/deseos")
async def obtener_lista_deseos(
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:usuario:deseos:{usuario_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        respuesta = supabase.table("deseos") \
            .select("id, id_producto, agregado_en, productos(nombre, slug, precio_normal, precio_oferta, imagen_principal, stock)") \
            .eq("id_usuario", usuario_id).order("agregado_en", desc=True).execute()
            
        deseos_formateados = []
        for d in respuesta.data:
            prod = d.get("productos")
            if isinstance(prod, list) and len(prod) > 0:
                prod = prod[0]
                
            if prod and isinstance(prod, dict):
                stock_bd = prod.get("stock")
                stock_numero = int(stock_bd) if stock_bd is not None else 0
                imagen_db = prod.get("imagen_principal")
                imagen_final = imagen_db if imagen_db else "src/images/products/img-01.png"
                deseos_formateados.append({
                    "id_deseo": d["id"],
                    "id_producto": d["id_producto"],
                    "nombre": prod.get("nombre", "Producto"),
                    "slug": prod.get("slug", ""), 
                    "precio": prod.get("precio_normal", 0),
                    "precio_oferta": prod.get("precio_oferta"),
                    "imagen": imagen_final,
                    "en_stock": stock_numero > 0
                })
                
        await redis_client.setex(cache_key, 900, json.dumps(deseos_formateados))
        return deseos_formateados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener deseos: {str(e)}")
    
@router.delete("/deseos/{id_producto}")
async def eliminar_de_deseos(
    id_producto: str, 
    usuario_id: str = Depends(obtener_usuario_actual), 
    redis_client: Redis = Depends(get_redis)
):
    try:
        supabase.table("deseos") \
            .delete() \
            .match({"id_usuario": usuario_id, "id_producto": id_producto}) \
            .execute()
            
        await limpiar_cache_deseos(redis_client, usuario_id)
        return {"mensaje": "Producto eliminado de la lista de deseos"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error al eliminar el producto")

@router.post("/deseos/{producto_id}")
async def alternar_lista_deseos(
    producto_id: str, 
    usuario = Depends(obtener_usuario_actual), 
    redis_client: Redis = Depends(get_redis)
):
    try:
        producto_id = producto_id.strip()
        uid = None
        if isinstance(usuario, dict):
            uid = usuario.get("id") or usuario.get("sub") or usuario.get("id_usuario")
        else:
            uid = getattr(usuario, "id", None) or getattr(usuario, "sub", None)
            
        if not uid:
            uid = str(usuario) 
            
        uid = str(uid).strip()
        existe = supabase.table("deseos").select("id").eq("id_usuario", uid).eq("id_producto", producto_id).execute()
        if existe.data:
            supabase.table("deseos").delete().eq("id", existe.data[0]["id"]).execute()
            await limpiar_cache_deseos(redis_client, uid)
            return {"mensaje": "Producto eliminado de favoritos", "agregado": False}
        else:
            supabase.table("deseos").insert({"id_usuario": uid, "id_producto": producto_id}).execute()
            await limpiar_cache_deseos(redis_client, uid)
            return {"mensaje": "Producto agregado a favoritos", "agregado": True}
    except Exception as e:
        print(f"🔥 ERROR EN FAVORITOS: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[UsuarioAdminResponse], dependencies=[Depends(rate_limiter(max_requests=60, window_seconds=60))])
async def listar_usuarios_admin(
    usuario_id: str = Depends(verificar_permiso("usuarios_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:usuarios_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    try:
        res = supabase_admin.table("usuarios").select("id, nombres, apellidos, correo, estado, mfa_activo, creado_en, id_rol, roles(nombre)").execute()
        usuarios = []
        for row in res.data:
            nombre_rol = "cliente"
            if row.get("roles") and row["roles"].get("nombre"):
                nombre_rol = row["roles"]["nombre"].lower()
                
            usuarios.append(UsuarioAdminResponse(
                id=row["id"],
                nombres=row.get("nombres", "Sin nombre"),
                apellidos=row.get("apellidos", "Sin apellido"),
                correo=row.get("correo", ""),
                rol=nombre_rol,
                estado=row.get("estado", "activo"),
                mfa_activo=row.get("mfa_activo", False),
                creado_en=row.get("creado_en")
            ))

        await redis_client.setex(cache_key, 900, json.dumps(jsonable_encoder(usuarios)))
        return usuarios
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print("\n🚨 ERROR CRÍTICO EN MÓDULO DE USUARIOS 🚨")
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=f"Error al obtener usuarios: {str(e)}")
    
@router.post("/admin-crear", status_code=status.HTTP_201_CREATED)
async def crear_usuario_por_admin(
    datos: CrearUsuarioAdminRequest,
    admin_id: str = Depends(verificar_permiso("usuarios_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        admin_db = supabase.table("usuarios").select("correo").eq("id", admin_id).single().execute()
        if not admin_db.data:
            raise HTTPException(status_code=404, detail="Administrador no encontrado.")
        
        admin_email = admin_db.data["correo"]
        try:
            auth_check = supabase.auth.sign_in_with_password({
                "email": admin_email,
                "password": datos.confirmacion_contrasena_admin
            })

            if not auth_check.user:
                raise ValueError()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La contraseña de confirmación del administrador es incorrecta."
            )

        nombre_rol_buscar = datos.rol.strip().lower()
        rol_res = supabase.table("roles").select("id").ilike("nombre", nombre_rol_buscar).execute()
        if not rol_res.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"El rol '{datos.rol}' no existe en el sistema."
            )

        id_rol = rol_res.data[0]["id"]
        try:
            nuevo_auth = supabase_admin.auth.admin.create_user({
                "email": datos.correo,
                "password": datos.contrasena_usuario,
                "email_confirm": True
            })
            new_user_id = nuevo_auth.user.id
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error en Supabase Auth: {str(e)}")

        try:
            nuevo_usuario_db = {
                "id": new_user_id,
                "id_rol": id_rol,
                "nombres": datos.nombres,
                "apellidos": datos.apellidos,
                "correo": datos.correo
            }

            supabase_admin.table("usuarios").insert(nuevo_usuario_db).execute()
            try:
                autor = obtener_nombre_usuario(admin_id)
                notificar_administradores(
                    tipo="usuario",
                    titulo="Usuario Creado Manualmente",
                    mensaje=f"{autor} ha registrado la cuenta '{datos.correo}' con el rol '{datos.rol}'.",
                    enlace="usuarios.html"
                )
            except Exception as e:
                print(f"[ERROR NOTIFICACIÓN] {e}")
            await limpiar_cache_usuario(redis_client)
            return {"mensaje": "Usuario registrado exitosamente por el administrador.", "usuario_id": new_user_id}
        except Exception as e:
            supabase_admin.auth.admin.delete_user(new_user_id)
            raise HTTPException(status_code=500, detail=f"Error al guardar datos de perfil: {str(e)}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{usuario_id}")
async def editar_usuario_admin(
    usuario_id: str,
    datos: EditarUsuarioAdminRequest,
    admin_id: str = Depends(verificar_permiso("usuarios_edit")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        rol_res = supabase.table("roles").select("id").ilike("nombre", datos.rol).execute()
        if not rol_res.data:
            raise HTTPException(status_code=400, detail="El rol especificado no existe.")
        
        id_rol = rol_res.data[0]["id"]
        supabase_admin.auth.admin.update_user_by_id(usuario_id, {"email": datos.correo})
        supabase.table("usuarios").update({
            "nombres": datos.nombres,
            "apellidos": datos.apellidos,
            "correo": datos.correo,
            "id_rol": id_rol
        }).eq("id", usuario_id).execute()
        
        try:
            autor = obtener_nombre_usuario(admin_id)
            notificar_administradores(
                tipo="usuario",
                titulo="Usuario Modificado",
                mensaje=f"{autor} ha editado los datos y/o rol del usuario '{datos.correo}'.",
                enlace="usuarios.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
            
        await limpiar_cache_usuario(redis_client, usuario_id)
        return {"mensaje": "Usuario actualizado exitosamente."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar: {str(e)}")

@router.put("/toggle-estado/{usuario_id}")
async def alternar_estado_usuario(
    usuario_id: str,
    admin_id: str = Depends(verificar_permiso("usuarios_delete")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        usr = supabase_admin.table("usuarios").select("estado, correo").eq("id", usuario_id).single().execute()
        if not usr.data:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        nuevo_estado = "oculto" if usr.data.get("estado") == "activo" else "activo"
        correo_usuario = usr.data.get("correo", "Desconocido")
        supabase_admin.table("usuarios").update({"estado": nuevo_estado}).eq("id", usuario_id).execute()

        try:
            autor = obtener_nombre_usuario(admin_id)
            accion = "activado" if nuevo_estado == "activo" else "suspendido"
            notificar_administradores(
                tipo="usuario",
                titulo=f"Cuenta de Usuario {accion.capitalize()}a",
                mensaje=f"{autor} ha {accion} la cuenta de '{correo_usuario}'.",
                enlace="usuarios.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
            
        await limpiar_cache_usuario(redis_client, usuario_id)
        return {"mensaje": f"Estado del usuario cambiado a {nuevo_estado}.", "nuevo_estado": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al cambiar estado: {str(e)}")
    
@router.get("/puede-comentar/{id_producto}")
def verificar_permiso_comentario(id_producto: str, usuario_id: str = Depends(obtener_usuario_actual)):
    try:
        print(f"[DEBUG RESEÑAS] Verificando usuario: {usuario_id} | Producto: {id_producto}")
        pedidos_res = supabase_admin.table("pedidos").select("id").eq("id_cliente", usuario_id).execute()
        
        if not pedidos_res.data:
            print("[DEBUG RESEÑAS] El usuario no tiene ningún pedido registrado.")
            return {"puede_comentar": False}
            
        ids_pedidos = [p["id"] for p in pedidos_res.data]
        print(f"[DEBUG RESEÑAS] IDs de Pedidos encontrados: {ids_pedidos}")
        detalles_res = supabase_admin.table("detalle_pedido") \
            .select("id") \
            .in_("id_pedido", ids_pedidos) \
            .eq("id_producto", id_producto) \
            .execute()

        compro_producto = len(detalles_res.data) > 0
        print(f"[DEBUG RESEÑAS] ¿Encontró el producto en los detalles?: {compro_producto}")
        
        return {"puede_comentar": compro_producto}
    except Exception as e:
        print(f"Error verificando permisos: {e}")
        return {"puede_comentar": False}
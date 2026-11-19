import json
from typing import List, Optional
from pydantic import BaseModel
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import obtener_usuario_actual, verificar_permiso
from app.services.email_brevo import enviar_correo_estado_pedido
from app.services.notificaciones_service import notificar_administradores
from redis.asyncio import Redis
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks, UploadFile, File, Form
from datetime import datetime, timezone
import uuid

router = APIRouter()

class ActualizarEstadoRequest(BaseModel):
    estado: str

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = (
            supabase_admin.table("usuarios")
            .select("nombres, apellidos")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception as e:
        print(f"[DEBUG PEDIDOS] No se pudo obtener el nombre del usuario: {e}")
    return "Un administrador"


@router.get("/pedidos")
async def listar_pedidos_admin(
    usuario_id: str = Depends(verificar_permiso("pedidos_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:pedidos_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = (
            supabase_admin.table("pedidos")
            .select(
                "id, total, estado, fecha_hora_pedido, metodo_despacho, "
                "usuarios(nombres, apellidos, correo, roles(nombre))"
            )
            .order("fecha_hora_pedido", desc=True)
            .execute()
        )
        if res.data:
            await redis_client.setex(cache_key, 900, json.dumps(res.data))
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pedidos/conteo-procesando")
def obtener_conteo_pedidos_procesando(
    usuario_id: str = Depends(verificar_permiso("pedidos_access"))
):
    try:
        res = (
            supabase_admin.table("pedidos")
            .select("id", count="exact")
            .ilike("estado", "procesando")
            .execute()
        )
        total = res.count if res.count is not None else 0
        return {"procesando": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pedidos/{pedido_id}")
async def obtener_detalle_pedido_admin(
    pedido_id: str,
    usuario_id: str = Depends(verificar_permiso("pedidos_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:admin:pedido_detalle:{pedido_id}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res_pedido = (
            supabase_admin.table("pedidos")
            .select(
                "*, cupones(codigo_cupon), "
                "usuarios(nombres, apellidos, correo, telefono, "
                "tipo_documento, numero_documento, direccion, "
                "departamento, provincia, distrito)"
            )
            .eq("id", pedido_id)
            .single()
            .execute()
        )

        if not res_pedido.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        pedido = res_pedido.data

        res_venta = (
            supabase_admin.table("ventas")
            .select("metodo_pago")
            .eq("id_pedido", pedido_id)
            .execute()
        )
        metodo_pago = (
            res_venta.data[0].get("metodo_pago", "Mercado Pago")
            if res_venta.data
            else "Mercado Pago"
        )

        res_detalles = (
            supabase_admin.table("detalle_pedido")
            .select(
                "cantidad, precio_unitario, subtotal, "
                "productos(nombre, sku, imagen_principal)"
            )
            .eq("id_pedido", pedido_id)
            .execute()
        )

        # Obtener solicitud de cancelación / reembolso si existe
        res_solicitud = (
            supabase_admin.table("solicitudes_reembolso")
            .select("*")
            .eq("id_pedido", pedido_id)
            .execute()
        )
        solicitud = res_solicitud.data[0] if res_solicitud.data else None

        resultado = {
            "pedido": pedido,
            "metodo_pago": metodo_pago,
            "productos": res_detalles.data,
            "solicitud_reembolso": solicitud
        }

        await redis_client.setex(cache_key, 900, json.dumps(resultado))
        return resultado

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/pedidos/{pedido_id}/estado")
async def actualizar_estado_pedido(
    pedido_id: str,
    datos: ActualizarEstadoRequest,
    background_tasks: BackgroundTasks,
    usuario_id: str = Depends(verificar_permiso("pedidos_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        # 1. Validación de seguridad: verificar estado actual antes de editar
        res_actual = (
            supabase_admin.table("pedidos")
            .select("estado")
            .eq("id", pedido_id)
            .single()
            .execute()
        )
        if not res_actual.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if (res_actual.data.get("estado") or "").lower() == "reembolsado":
            raise HTTPException(
                status_code=400,
                detail="Este pedido ya fue marcado como REEMBOLSADO y no puede volver a editarse."
            )

        nuevo_estado = datos.estado.lower()

        res = (
            supabase_admin.table("pedidos")
            .update({"estado": nuevo_estado})
            .eq("id", pedido_id)
            .execute()
        )

        if not res.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if nuevo_estado == "reembolsado":
            (
                supabase_admin.table("ventas")
                .update({"estado_pago": "reembolsado"})
                .eq("id_pedido", pedido_id)
                .execute()
            )

        res_cliente = (
            supabase_admin.table("pedidos")
            .select("usuarios(nombres, apellidos, correo)")
            .eq("id", pedido_id)
            .single()
            .execute()
        )

        if res_cliente.data and res_cliente.data.get("usuarios"):
            usuario = res_cliente.data["usuarios"]
            correo_destino = usuario.get("correo")
            nombres = usuario.get("nombres") or ""
            apellidos = usuario.get("apellidos") or ""
            nombre_completo = f"{nombres} {apellidos}".strip() or "Cliente"

            if correo_destino:
                background_tasks.add_task(
                    enviar_correo_estado_pedido,
                    email_destino=correo_destino,
                    nombre_cliente=nombre_completo,
                    pedido_id=pedido_id,
                    nuevo_estado=nuevo_estado
                )

        try:
            autor = obtener_nombre_usuario(usuario_id)
            pedido_corto = pedido_id.split("-")[0].upper()

            notificar_administradores(
                tipo="sistema",
                titulo="Estado de Pedido Actualizado",
                mensaje=(
                    f"{autor} cambió el estado del pedido "
                    f"#PED-{pedido_corto} a '{nuevo_estado.upper()}'."
                ),
                enlace="detalle-pedido.html?id=" + pedido_id
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:pedidos_lista")
        await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")
        await redis_client.delete("cache:dashboard:estadisticas")
        await redis_client.delete("cache:admin:ventas_historial")

        return {
            "message": "Estado actualizado correctamente",
            "estado": nuevo_estado
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pedidos/{pedido_id}/comprobante")
async def subir_comprobante_pedido(
    pedido_id: str,
    archivo: UploadFile = File(...),
    usuario_id: str = Depends(verificar_permiso("pedidos_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        res_pedido = supabase_admin.table("pedidos")\
            .select("id, estado, tipo_comprobante, comprobante_url")\
            .eq("id", pedido_id)\
            .single()\
            .execute()

        if not res_pedido.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if (res_pedido.data.get("estado") or "").lower() == "reembolsado":
            raise HTTPException(
                status_code=400,
                detail="No se puede modificar el comprobante de un pedido ya reembolsado."
            )

        tipos_permitidos = ["application/pdf", "image/jpeg", "image/png", "image/webp"]
        if archivo.content_type not in tipos_permitidos:
            raise HTTPException(
                status_code=400,
                detail="Formato no permitido. Solo se aceptan archivos PDF, JPG, PNG o WEBP."
            )

        contenido = await archivo.read()
        if len(contenido) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="El archivo supera el límite máximo de 5 MB.")

        extension = archivo.filename.split(".")[-1].lower() if "." in archivo.filename else "pdf"
        tipo_doc = (res_pedido.data.get("tipo_comprobante") or "boleta").upper()
        pedido_corto = pedido_id.split("-")[0].upper()
        nombre_limpio = f"{tipo_doc}_PED-{pedido_corto}_{uuid.uuid4().hex[:6]}.{extension}"
        ruta_storage = f"pedidos/{pedido_id}/{nombre_limpio}"

        supabase_admin.storage.from_("comprobantes").upload(
            path=ruta_storage,
            file=contenido,
            file_options={"content-type": archivo.content_type, "upsert": "true"}
        )

        url_publica = supabase_admin.storage.from_("comprobantes").get_public_url(ruta_storage)
        ahora = datetime.now(timezone.utc).isoformat()

        supabase_admin.table("pedidos").update({
            "comprobante_url": url_publica,
            "comprobante_nombre": archivo.filename,
            "comprobante_fecha": ahora
        }).eq("id", pedido_id).execute()

        await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")

        return {
            "message": "Comprobante subido y vinculado correctamente.",
            "comprobante_url": url_publica,
            "comprobante_nombre": archivo.filename,
            "comprobante_fecha": ahora
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir comprobante: {str(e)}")


@router.post("/pedidos/{pedido_id}/responder-solicitud")
async def responder_solicitud_reembolso(
    pedido_id: str,
    respuesta_admin: str = Form(...),
    estado_resolucion: str = Form("aprobada"),  # 'aprobada' o 'rechazada'
    archivos: Optional[List[UploadFile]] = File(None),
    usuario_id: str = Depends(verificar_permiso("pedidos_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        mensaje_limpio = (respuesta_admin or "").strip()
        if len(mensaje_limpio) < 5:
            raise HTTPException(status_code=400, detail="Debes escribir un mensaje de respuesta válido.")

        if estado_resolucion not in ["aprobada", "rechazada"]:
            raise HTTPException(status_code=400, detail="Estado de resolución inválido.")

        # 1. Buscar la solicitud y verificar que no haya sido respondida ya
        res_sol = (
            supabase_admin.table("solicitudes_reembolso")
            .select("*")
            .eq("id_pedido", pedido_id)
            .single()
            .execute()
        )

        if not res_sol.data:
            raise HTTPException(status_code=404, detail="No existe una solicitud de reembolso para este pedido.")

        solicitud = res_sol.data
        if solicitud.get("estado") != "pendiente" or solicitud.get("fecha_respuesta") is not None:
            raise HTTPException(
                status_code=400,
                detail="Esta solicitud ya fue respondida anteriormente y no puede volver a modificarse."
            )

        # 2. Validar y subir hasta un máximo de 3 archivos opcionales
        archivos_validos = [a for a in (archivos or []) if a and a.filename]
        if len(archivos_validos) > 3:
            raise HTTPException(status_code=400, detail="Solo puedes subir un máximo de 3 archivos adjuntos.")

        tipos_permitidos = [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
            "text/xml",
            "application/xml"
        ]

        adjuntos_guardados = []
        for archivo in archivos_validos:
            if archivo.content_type not in tipos_permitidos:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato no permitido en '{archivo.filename}'. Solo PDF, JPG, PNG, WEBP o XML."
                )

            contenido = await archivo.read()
            if len(contenido) > 5 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo '{archivo.filename}' supera el máximo de 5 MB."
                )

            ext = archivo.filename.split(".")[-1].lower() if "." in archivo.filename else "pdf"
            nombre_storage = f"RES_{uuid.uuid4().hex[:10]}.{ext}"
            ruta_storage = f"reembolsos/{pedido_id}/{nombre_storage}"

            supabase_admin.storage.from_("documentos-reembolsos").upload(
                path=ruta_storage,
                file=contenido,
                file_options={"content-type": archivo.content_type, "upsert": "false"}
            )

            url_publica = supabase_admin.storage.from_("documentos-reembolsos").get_public_url(ruta_storage)
            adjuntos_guardados.append({
                "nombre": archivo.filename,
                "url": url_publica,
                "tipo": archivo.content_type
            })

        ahora = datetime.now(timezone.utc).isoformat()
        res_update = (
            supabase_admin.table("solicitudes_reembolso")
            .update({
                "estado": estado_resolucion,
                "id_admin_respuesta": usuario_id,
                "respuesta_admin": mensaje_limpio,
                "archivos_adjuntos": adjuntos_guardados,
                "fecha_respuesta": ahora
            })
            .eq("id", solicitud["id"])
            .eq("estado", "pendiente")
            .execute()
        )

        try:
            pedido_corto = pedido_id.split("-")[0].upper()
            supabase_admin.table("notificaciones").insert({
                "id_usuario": solicitud["id_cliente"],
                "tipo": "pedido",
                "titulo": f"Respuesta a tu solicitud (#PED-{pedido_corto})",
                "mensaje": f"Administración ha respondido tu solicitud de {solicitud['tipo_solicitud']}.",
                "enlace": f"detalles-del-pedido.html?id={pedido_id}"
            }).execute()
        except Exception as e:
            print(f"[ERROR NOTIF CLIENTE REEMBOLSO] {e}")

        await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")
        await redis_client.delete("cache:admin:pedidos_lista")

        return {
            "message": "Respuesta enviada al cliente correctamente.",
            "solicitud": res_update.data[0] if res_update.data else None
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR RESPONDER SOLICITUD]: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al procesar la respuesta: {str(e)}")
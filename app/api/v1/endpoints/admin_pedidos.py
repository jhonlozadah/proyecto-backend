from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from typing import Optional
import json
from pydantic import BaseModel
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import obtener_usuario_actual, verificar_permiso
from app.services.email_brevo import enviar_correo_estado_pedido
from app.services.notificaciones_service import notificar_administradores
from redis.asyncio import Redis

router = APIRouter()

class ActualizarEstadoRequest(BaseModel):
    estado: str
    motivo: Optional[str] = None
    reingresar_stock: Optional[bool] = True

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
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
        print("[DEBUG] Lista de pedidos servida desde Redis ⚡")
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("pedidos")\
            .select("id, total, estado, fecha_hora_pedido, metodo_despacho, usuarios(nombres, apellidos, correo, roles(nombre))")\
            .order("fecha_hora_pedido", desc=True)\
            .execute()
            
        if res.data:
            await redis_client.setex(cache_key, 900, json.dumps(res.data))
            
        return res.data
    except HTTPException as he:
        raise he
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
        print(f"[ERROR CONTEO PEDIDOS]: {str(e)}")
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
        print(f"[DEBUG] Detalle del pedido {pedido_id} servido desde Redis")
        return json.loads(cached_data)

    try:
        res_pedido = supabase_admin.table("pedidos")\
            .select("*, cupones(codigo_cupon), usuarios(nombres, apellidos, correo, telefono, tipo_documento, numero_documento, direccion, departamento, provincia, distrito)")\
            .eq("id", pedido_id)\
            .single()\
            .execute()

        if not res_pedido.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        pedido = res_pedido.data
        res_venta = supabase_admin.table("ventas").select("id, metodo_pago, estado_pago").eq("id_pedido", pedido_id).execute()
        metodo_pago = res_venta.data[0].get("metodo_pago", "Mercado Pago") if res_venta.data else "Mercado Pago"
        
        res_detalles = supabase_admin.table("detalle_pedido")\
            .select("cantidad, precio_unitario, subtotal, productos(nombre, sku, imagen_principal)")\
            .eq("id_pedido", pedido_id)\
            .execute()

        # Consultar si el pedido ya tiene una Nota de Crédito emitida
        res_nc = supabase_admin.table("notas_credito")\
            .select("*")\
            .eq("id_pedido", pedido_id)\
            .execute()
        nota_credito = res_nc.data[0] if res_nc.data else None

        resultado = {
            "pedido": pedido,
            "metodo_pago": metodo_pago,
            "productos": res_detalles.data,
            "nota_credito": nota_credito
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
        nuevo_estado = datos.estado.lower().strip()

        # Obtener datos actuales del pedido antes de actualizar
        res_pedido_actual = supabase_admin.table("pedidos")\
            .select("id, id_cliente, total, estado, tipo_comprobante, ruc_factura, razon_social_factura, usuarios(nombres, apellidos, correo)")\
            .eq("id", pedido_id)\
            .single()\
            .execute()

        if not res_pedido_actual.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        pedido_actual = res_pedido_actual.data
        estado_anterior = (pedido_actual.get("estado") or "").lower()

        # Actualizar estado en la tabla pedidos
        res = supabase_admin.table("pedidos")\
            .update({"estado": nuevo_estado})\
            .eq("id", pedido_id)\
            .execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="No se pudo actualizar el pedido")

        nota_credito_emitida = None

        # Flujo de Reembolso / Cancelación con Nota de Crédito
        if nuevo_estado in ["reembolsado", "cancelado"]:
            motivo_texto = (datos.motivo or "").strip() or "Anulación de la operación y reembolso al cliente."
            reingresar = True if datos.reingresar_stock is None else bool(datos.reingresar_stock)

            # 1. Actualizar venta a reembolsado
            res_venta = supabase_admin.table("ventas")\
                .update({"estado_pago": "reembolsado"})\
                .eq("id_pedido", pedido_id)\
                .execute()

            venta_id = res_venta.data[0]["id"] if res_venta.data else None

            # 2. Verificar si aún no existe una Nota de Crédito para evitar duplicados
            nc_existente = supabase_admin.table("notas_credito")\
                .select("*")\
                .eq("id_pedido", pedido_id)\
                .execute()

            if not nc_existente.data:
                tipo_comp = (pedido_actual.get("tipo_comprobante") or "boleta").lower()
                serie_nc = "FC01" if tipo_comp == "factura" else "BC01"

                nueva_nc = {
                    "serie": serie_nc,
                    "id_pedido": pedido_id,
                    "id_venta": venta_id,
                    "id_cliente": pedido_actual["id_cliente"],
                    "tipo_comprobante_ref": tipo_comp,
                    "ruc_cliente": pedido_actual.get("ruc_factura"),
                    "razon_social_cliente": pedido_actual.get("razon_social_factura"),
                    "motivo": motivo_texto,
                    "monto_devuelto": float(pedido_actual["total"]),
                    "stock_reingresado": reingresar,
                    "estado": "emitida"
                }

                res_nc = supabase_admin.table("notas_credito").insert(nueva_nc).execute()
                if res_nc.data:
                    nota_credito_emitida = res_nc.data[0]

                # 3. Devolver stock al inventario si corresponde y no estaba ya anulado
                if reingresar and estado_anterior not in ["reembolsado", "cancelado"]:
                    detalles = supabase_admin.table("detalle_pedido")\
                        .select("id_producto, cantidad")\
                        .eq("id_pedido", pedido_id)\
                        .execute()

                    for item in (detalles.data or []):
                        prod = supabase_admin.table("productos")\
                            .select("stock")\
                            .eq("id", item["id_producto"])\
                            .single()\
                            .execute()
                        if prod.data is not None:
                            nuevo_stock = int(prod.data.get("stock") or 0) + int(item["cantidad"] or 0)
                            supabase_admin.table("productos")\
                                .update({"stock": nuevo_stock})\
                                .eq("id", item["id_producto"])\
                                .execute()

                    # Limpiar caché de productos para reflejar el stock restaurado en tienda
                    keys_prod = await redis_client.keys("cache:productos:*")
                    if keys_prod:
                        await redis_client.delete(*keys_prod)
                    await redis_client.delete("cache:admin:productos_lista")
            else:
                nota_credito_emitida = nc_existente.data[0]

        # Envío de correo al cliente vía Brevo
        if pedido_actual.get("usuarios"):
            usuario = pedido_actual["usuarios"]
            correo_destino = usuario.get("correo")
            nombres = usuario.get('nombres') or ''
            apellidos = usuario.get('apellidos') or ''
            nombre_completo = f"{nombres} {apellidos}".strip() or "Cliente"

            if correo_destino:
                background_tasks.add_task(
                    enviar_correo_estado_pedido,
                    email_destino=correo_destino,
                    nombre_cliente=nombre_completo,
                    pedido_id=pedido_id,
                    nuevo_estado=nuevo_estado
                )

        # Notificación interna en el panel administrativo
        try:
            autor = obtener_nombre_usuario(usuario_id)
            pedido_corto = pedido_id.split("-")[0].upper()
            extra_nc = f" (Nota de Crédito {nota_credito_emitida['codigo_nota']} emitida)" if nota_credito_emitida else ""
            notificar_administradores(
                tipo="sistema",
                titulo="Estado de Pedido Actualizado",
                mensaje=f"{autor} cambió el estado del pedido #PED-{pedido_corto} a '{nuevo_estado.upper()}'{extra_nc}.",
                enlace="detalle-pedido.html?id=" + pedido_id
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        # Invalidar cachés de Redis
        await redis_client.delete("cache:admin:pedidos_lista")
        await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")
        await redis_client.delete("cache:dashboard:estadisticas")
        await redis_client.delete("cache:admin:ventas_historial")

        return {
            "message": "Estado actualizado correctamente",
            "estado": nuevo_estado,
            "nota_credito": nota_credito_emitida
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
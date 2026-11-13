from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
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
        res_venta = supabase_admin.table("ventas").select("metodo_pago").eq("id_pedido", pedido_id).execute()
        metodo_pago = res_venta.data[0].get("metodo_pago", "Mercado Pago") if res_venta.data else "Mercado Pago"
        
        res_detalles = supabase_admin.table("detalle_pedido")\
            .select("cantidad, precio_unitario, subtotal, productos(nombre, sku, imagen_principal)")\
            .eq("id_pedido", pedido_id)\
            .execute()

        resultado = {
            "pedido": pedido,
            "metodo_pago": metodo_pago,
            "productos": res_detalles.data
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
        nuevo_estado = datos.estado.lower()
        
        res = supabase_admin.table("pedidos")\
            .update({"estado": nuevo_estado})\
            .eq("id", pedido_id)\
            .execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if nuevo_estado == "reembolsado":
            supabase_admin.table("ventas")\
                .update({"estado_pago": "reembolsado"})\
                .eq("id_pedido", pedido_id)\
                .execute()

        res_cliente = supabase_admin.table("pedidos")\
            .select("usuarios(nombres, apellidos, correo)")\
            .eq("id", pedido_id)\
            .single()\
            .execute()

        if res_cliente.data and res_cliente.data.get("usuarios"):
            usuario = res_cliente.data["usuarios"]
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

        try:
            autor = obtener_nombre_usuario(usuario_id)
            pedido_corto = pedido_id.split("-")[0].upper()
            notificar_administradores(
                tipo="sistema",
                titulo="Estado de Pedido Actualizado",
                mensaje=f"{autor} cambió el estado del pedido #PED-{pedido_corto} a '{nuevo_estado.upper()}'.",
                enlace="detalle-pedido.html?id=" + pedido_id
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:pedidos_lista")
        await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")
        await redis_client.delete("cache:dashboard:estadisticas")
        await redis_client.delete("cache:admin:ventas_historial")
        return {"message": "Estado actualizado correctamente", "estado": nuevo_estado}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/conteo-procesando")
def obtener_conteo_pedidos_procesando(usuario = Depends(obtener_usuario_actual)):
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
        print(f"[ERROR CONTEO PEDIDOS]: {e}")
        return {"procesando": 0}
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from app.schemas.pedido_schema import CrearPedidoRequest
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import obtener_usuario_actual
from app.services.pedido_service import procesar_nueva_orden
from app.services.notificaciones_service import notificar_administradores
from redis.asyncio import Redis

router = APIRouter()

class SolicitudReembolsoRequest(BaseModel):
    tipo_solicitud: str = Field(..., pattern="^(cancelacion|reembolso)$")
    motivo_categoria: str = Field(..., min_length=3, max_length=100)
    motivo_detalle: str = Field(..., min_length=10, max_length=1000)
    acepto_terminos: bool

@router.post("/crear-preferencia")
def crear_preferencia_endpoint(
    datos: CrearPedidoRequest,
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    try:
        link_pago = procesar_nueva_orden(datos=datos, token=token, user_id=usuario_id)
        return {"init_point": link_pago}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pedidos/{pedido_id}")
def obtener_detalle_pedido(
    pedido_id: str,
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    res_pedido = supabase_admin.table("pedidos")\
        .select("*, usuarios(nombres, apellidos, correo, telefono, tipo_documento, numero_documento, departamento, provincia, distrito, direccion)")\
        .eq("id", pedido_id)\
        .single()\
        .execute()

    if not res_pedido.data:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    pedido = res_pedido.data

    if str(pedido.get("id_cliente")) != str(usuario_id):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este pedido")

    res_venta = supabase_admin.table("ventas")\
        .select("metodo_pago")\
        .eq("id_pedido", pedido_id)\
        .execute()

    metodo_pago = "Mercado Pago"
    if res_venta.data and len(res_venta.data) > 0:
        metodo_pago = res_venta.data[0].get("metodo_pago", "Mercado Pago")

    res_detalles = supabase_admin.table("detalle_pedido")\
        .select("cantidad, precio_unitario, subtotal, productos(id, nombre, imagen_principal)")\
        .eq("id_pedido", pedido_id)\
        .execute()

    detalles = res_detalles.data or []
    subtotal_productos = sum(float(item["subtotal"]) for item in detalles)

    res_solicitud = supabase_admin.table("solicitudes_reembolso")\
        .select("id, tipo_solicitud, motivo_categoria, motivo_detalle, estado, fecha_solicitud, respuesta_admin, archivos_adjuntos, fecha_respuesta")\
        .eq("id_pedido", pedido_id)\
        .eq("id_cliente", usuario_id)\
        .execute()

    solicitud = res_solicitud.data[0] if res_solicitud.data else None

    return {
        "pedido": pedido,
        "metodo_pago": metodo_pago,
        "subtotal": subtotal_productos,
        "productos": detalles,
        "solicitud_reembolso": solicitud
    }

@router.post("/pedidos/{pedido_id}/solicitud-reembolso")
async def crear_solicitud_reembolso(
    pedido_id: str,
    datos: SolicitudReembolsoRequest,
    usuario_id: str = Depends(obtener_usuario_actual),
    redis_client: Redis = Depends(get_redis)
):
    if not datos.acepto_terminos:
        raise HTTPException(
            status_code=400,
            detail="Debes marcar la casilla de confirmación indicando que comprendes que esta acción es irreversible."
        )

    res_pedido = supabase_admin.table("pedidos")\
        .select("id, id_cliente, estado, total, usuarios(nombres, apellidos)")\
        .eq("id", pedido_id)\
        .single()\
        .execute()

    if not res_pedido.data:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    pedido = res_pedido.data
    if str(pedido.get("id_cliente")) != str(usuario_id):
        raise HTTPException(status_code=403, detail="No tienes permiso para operar sobre este pedido.")

    estado_actual = (pedido.get("estado") or "").lower()
    if estado_actual in ["cancelado", "reembolsado"]:
        raise HTTPException(
            status_code=400,
            detail=f"Este pedido ya se encuentra en estado '{estado_actual}' y no admite nuevas solicitudes."
        )

    existe = supabase_admin.table("solicitudes_reembolso")\
        .select("id")\
        .eq("id_pedido", pedido_id)\
        .execute()

    if existe.data:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una solicitud registrada para este pedido. No es posible enviar otra."
        )

    nueva_solicitud = {
        "id_pedido": pedido_id,
        "id_cliente": usuario_id,
        "tipo_solicitud": datos.tipo_solicitud,
        "motivo_categoria": datos.motivo_categoria.strip(),
        "motivo_detalle": datos.motivo_detalle.strip(),
        "acepto_terminos": True,
        "estado": "pendiente"
    }

    res_insert = supabase_admin.table("solicitudes_reembolso").insert(nueva_solicitud).execute()
    if not res_insert.data:
        raise HTTPException(status_code=500, detail="No se pudo registrar la solicitud.")

    try:
        u = pedido.get("usuarios") or {}
        nombre_cliente = f"{u.get('nombres', '')} {u.get('apellidos', '')}".strip() or "Un cliente"
        pedido_corto = pedido_id.split("-")[0].upper()

        notificar_administradores(
            tipo="pedido",
            titulo="Solicitud de Cancelación / Reembolso",
            mensaje=f"{nombre_cliente} solicitó {datos.tipo_solicitud} para el pedido #PED-{pedido_corto} ({datos.motivo_categoria}).",
            enlace=f"detalle-pedido.html?id={pedido_id}"
        )
    except Exception as e:
        print(f"[ERROR NOTIFICACIÓN SOLICITUD] {e}")

    await redis_client.delete(f"cache:admin:pedido_detalle:{pedido_id}")
    await redis_client.delete("cache:admin:pedidos_lista")

    return {
        "message": "Tu solicitud ha sido enviada al área de administración para su evaluación.",
        "solicitud": res_insert.data[0]
    }
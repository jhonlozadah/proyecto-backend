from fastapi import APIRouter, HTTPException, Request
from app.schemas.pedido_schema import CrearPedidoRequest
from app.core.database import supabase_admin
from app.api.dependencies import verificar_permiso, obtener_usuario_actual
from app.services.pedido_service import procesar_nueva_orden

router = APIRouter()

@router.post("/crear-preferencia")
def crear_preferencia_endpoint(datos: CrearPedidoRequest, request: Request):
    token = request.cookies.get("access_token")
    try:
        link_pago = procesar_nueva_orden(datos=datos, token=token)
        return {"init_point": link_pago}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pedidos/{pedido_id}")
def obtener_detalle_pedido(pedido_id: str, request: Request):
    res_pedido = supabase_admin.table("pedidos")\
        .select("*, usuarios(nombres, apellidos, correo, telefono, tipo_documento, numero_documento, departamento, provincia, distrito, direccion)")\
        .eq("id", pedido_id)\
        .single()\
        .execute()

    if not res_pedido.data:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    pedido = res_pedido.data
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

    return {
        "pedido": pedido,
        "metodo_pago": metodo_pago,
        "subtotal": subtotal_productos,
        "productos": detalles
    }
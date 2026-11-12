import json
from fastapi import APIRouter, Depends, Request
from app.core.database import supabase_admin, get_redis
from datetime import datetime
from redis.asyncio import Redis

router = APIRouter()

@router.get("/")
async def obtener_estadisticas_dashboard(
    request: Request,
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:dashboard:estadisticas"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        print("[DEBUG] Dashboard servido desde Redis")
        return json.loads(cached_data)

    print("[DEBUG] Calculando métricas pesadas desde Supabase 🐢")
    rol_res = supabase_admin.table("roles").select("id").eq("nombre", "cliente").execute()
    id_rol_cliente = rol_res.data[0]["id"] if rol_res.data else None
    total_clientes = 0
    if id_rol_cliente:
        clientes_res = supabase_admin.table("usuarios").select("id", count="exact").eq("id_rol", id_rol_cliente).execute()
        total_clientes = clientes_res.count if clientes_res.count else 0
        
    ventas_res = supabase_admin.table("ventas").select("monto_total, fecha_hora, metodo_pago").neq("estado_pago", "reembolsado").execute()
    ventas = ventas_res.data or []
    ingresos_totales = 0
    ventas_por_dia = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    metodos_pago = {} 
    ingresos_por_mes = {1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0, 8:0, 9:0, 10:0, 11:0, 12:0}
    for v in ventas:
        monto = float(v["monto_total"])
        ingresos_totales += monto
        metodo_raw = v.get("metodo_pago")
        if not metodo_raw or metodo_raw.strip() == "":
            metodo = "Mercado Pago"
        else:
            metodo = metodo_raw.strip().lower()
            nombres_comerciales = {
                "account_money": "Saldo Mercado Pago",
                "yape": "Yape",
                "visa": "Visa",
                "master": "Mastercard",
                "amex": "American Express",
                "diners": "Diners Club",
                "pagoefectivo": "PagoEfectivo"
            }

            metodo = nombres_comerciales.get(metodo, metodo.title())
        metodos_pago[metodo] = metodos_pago.get(metodo, 0) + 1
            
        if v.get("fecha_hora"):
            try:
                fecha = datetime.fromisoformat(v["fecha_hora"].replace("Z", "+00:00"))
                dia_semana = fecha.weekday()
                mes_actual = fecha.month
                ventas_por_dia[dia_semana] += 1
                ingresos_por_mes[mes_actual] += monto
            except Exception:
                pass

    array_ventas_dia = [ventas_por_dia[i] for i in range(7)]
    array_ingresos_mes = [ingresos_por_mes[i] for i in range(1, 13)] 
    prod_res = supabase_admin.table("productos").select("id", count="exact").execute()
    total_productos = prod_res.count if prod_res.count else 0
    pedidos_res = supabase_admin.table("pedidos").select("id", count="exact").execute()
    total_pedidos = pedidos_res.count if pedidos_res.count else 0
    pagos_completados = len(ventas)
    carritos_creados = total_pedidos
    inicio_checkout = total_pedidos
    pedidos_abandonados = total_pedidos - pagos_completados
    tasa_conversion = 0.0
    if total_clientes > 0:
        tasa_conversion = round((pagos_completados / total_clientes) * 100, 1)

    ticket_promedio = ingresos_totales / pagos_completados if pagos_completados > 0 else 0
    ltv = ingresos_totales / total_clientes if total_clientes > 0 else 0
    detalles_res = supabase_admin.table("detalle_pedido").select("id_producto, cantidad, subtotal, productos(nombre)").execute()
    detalles = detalles_res.data or []
    productos_ranking = {}
    for d in detalles:
        id_prod = d.get("id_producto")
        nombre_prod = d.get("productos", {}).get("nombre", "Producto Desconocido") if d.get("productos") else "Producto Desconocido"
        cantidad = int(d.get("cantidad", 0))
        subtotal = float(d.get("subtotal", 0))
        
        if id_prod not in productos_ranking:
            productos_ranking[id_prod] = {"nombre": nombre_prod, "cantidad": 0, "ingresos": 0}
            
        productos_ranking[id_prod]["cantidad"] += cantidad
        productos_ranking[id_prod]["ingresos"] += subtotal

    lista_ranking = list(productos_ranking.values())
    lista_ranking.sort(key=lambda x: x["ingresos"], reverse=True)
    top_5_productos = lista_ranking[:5]

    stock_res = supabase_admin.table("productos").select("nombre, id, stock").lte("stock", 10).order("stock", desc=False).limit(5).execute()
    alertas_stock = stock_res.data or []

    resultado = {
        "kpis": {
            "clientes": total_clientes,
            "ventas_totales": ingresos_totales,
            "productos": total_productos,
            "pedidos": total_pedidos,
            "aov": ticket_promedio,
            "ltv": ltv
        },

        "graficos": {
            "conversion": tasa_conversion,
            "ventas_por_dia": array_ventas_dia,
            "metodos_pago": metodos_pago,
            "ingresos_mes": array_ingresos_mes
        },

        "funnel": {
            "total": carritos_creados,
            "checkout": inicio_checkout,
            "completados": pagos_completados,
            "abandonados": pedidos_abandonados
        },

        "tablas": {
            "top_productos": top_5_productos,
            "alertas_stock": alertas_stock
        }
    }

    await redis_client.setex(
        cache_key,
        300, 
        json.dumps(resultado)
    )
    return resultado
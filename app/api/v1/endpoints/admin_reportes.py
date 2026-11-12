import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.api.dependencies import verificar_permiso
from redis.asyncio import Redis
from app.core.database import supabase_admin, get_redis

router = APIRouter()

class ReporteFiltros(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    metodo_pago: str
    metodo_despacho: str

@router.post("/generar")
async def generar_reporte(
    filtros: ReporteFiltros,
    usuario_id: str = Depends(verificar_permiso("reportes_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = f"cache:reportes:{filtros.fecha_inicio}:{filtros.fecha_fin}:{filtros.metodo_pago}:{filtros.metodo_despacho}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        print("[DEBUG] Reporte generado servido desde Redis ⚡")
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("ventas")\
            .select("*, pedidos(id, metodo_despacho, costo_envio, receptor_nombres, usuarios(nombres, apellidos, correo))")\
            .neq("estado_pago", "reembolsado")\
            .gte("fecha_hora", f"{filtros.fecha_inicio}T00:00:00")\
            .lte("fecha_hora", f"{filtros.fecha_fin}T23:59:59")\
            .order("fecha_hora", desc=True)\
            .execute()

        ventas_brutas = res.data or []
        ventas_filtradas = []

        for v in ventas_brutas:
            pedido = v.get("pedidos") or {}
            metodo_pago_db = (v.get("metodo_pago") or "").lower()
            
            if filtros.metodo_pago == "yape" and "yape" not in metodo_pago_db:
                continue
            if filtros.metodo_pago == "card" and "yape" in metodo_pago_db:
                continue

            metodo_despacho_db = (pedido.get("metodo_despacho") or "").lower()
            if filtros.metodo_despacho == "agency" and metodo_despacho_db not in ["despacho", "agencia"]:
                continue
            if filtros.metodo_despacho == "pickup" and metodo_despacho_db not in ["tienda", "recojo"]:
                continue

            ventas_filtradas.append(v)

        ingresos_totales = sum(float(v["monto_total"]) for v in ventas_filtradas)
        total_pedidos = len(ventas_filtradas)
        ticket_promedio = ingresos_totales / total_pedidos if total_pedidos > 0 else 0.0

        resultado = {
            "kpis": {
                "ingresos": round(ingresos_totales, 2),
                "pedidos": total_pedidos,
                "ticket": round(ticket_promedio, 2)
            },
            "raw_data": ventas_filtradas
        }

        await redis_client.setex(
            cache_key,
            300,
            json.dumps(resultado)
        )

        return resultado
    except HTTPException as he: 
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
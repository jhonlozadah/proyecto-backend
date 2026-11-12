from fastapi import APIRouter, Depends, HTTPException, status
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import verificar_permiso
import json
from redis.asyncio import Redis

router = APIRouter()

@router.get("/")
async def obtener_ventas_y_kpis(
    usuario_id: str = Depends(verificar_permiso("ventas_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:ventas_historial"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        print("[DEBUG] Historial de ventas servido desde Redis")
        return json.loads(cached_data)
    try:
        res = supabase_admin.table("ventas")\
            .select("*, pedidos(id, estado, receptor_nombres, usuarios(nombres, apellidos, correo)))")\
            .order("fecha_hora", desc=True)\
            .execute()
            
        ventas = res.data or []
        
        ventas_validas = [v for v in ventas if v.get("estado_pago") != "reembolsado"]
        ingresos_totales = sum(float(v["monto_total"]) for v in ventas_validas)
        total_ventas = len(ventas_validas)
        ticket_promedio = ingresos_totales / total_ventas if total_ventas > 0 else 0.0
        
        resultado = {
            "kpis": {
                "ingresos_totales": round(ingresos_totales, 2),
                "total_ventas": total_ventas,
                "ticket_promedio": round(ticket_promedio, 2)
            },
            "historial": ventas
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener el historial de ventas: {str(e)}"
        )
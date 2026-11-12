from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import datetime, timezone
from pydantic import BaseModel
from app.schemas.cupon_schema import CuponCreateRequest, CuponUpdateRequest, CuponResponse
from app.services.notificaciones_service import notificar_administradores
import json
from redis.asyncio import Redis
from app.core.database import supabase_admin, get_redis
from app.api.dependencies import verificar_permiso, rate_limiter

router = APIRouter()

class ValidarCuponRequest(BaseModel):
    codigo: str
    subtotal: float

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

@router.get("/", response_model=List[CuponResponse])
async def listar_cupones(
    usuario_id: str = Depends(verificar_permiso("cupones_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:cupones_lista"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        res = supabase_admin.table("cupones").select("*").order("fecha_inicio", desc=True).execute()
        if res.data:
            await redis_client.setex(cache_key, 900, json.dumps(res.data))
            
        return res.data
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar cupones: {str(e)}")

@router.post("/", status_code=status.HTTP_201_CREATED)
async def crear_cupon(
    datos: CuponCreateRequest,
    usuario_id: str = Depends(verificar_permiso("cupones_create")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        nuevo_cupon = {
            "codigo_cupon": datos.codigo_cupon.upper().strip(),
            "tipo_descuento": datos.tipo_descuento,
            "valor_descuento": datos.valor_descuento,
            "monto_minimo": datos.monto_minimo,
            "limite_usos": datos.limite_usos,
            "limite_uso_por_usuario": datos.limite_uso_por_usuario or 1,
            "fecha_inicio": datos.fecha_inicio.isoformat(),
            "fecha_expiracion": datos.fecha_expiracion.isoformat(),
            "estado": True
        }

        res = supabase_admin.table("cupones").insert(nuevo_cupon).execute()
        try:
            autor = obtener_nombre_usuario(usuario_id)
            notificar_administradores(
                tipo="sistema",
                titulo="Nuevo Cupón Creado",
                mensaje=f"{autor} ha creado el cupón '{nuevo_cupon['codigo_cupon']}'.",
                enlace="cupones.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:cupones_lista")
        return {"mensaje": "Cupón registrado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al registrar el cupón: {str(e)}")

@router.put("/{cupon_id}")
async def actualizar_cupon(
    cupon_id: str,
    datos: CuponUpdateRequest,
    usuario_id: str = Depends(verificar_permiso("cupones_edit")),
    redis_client: Redis = Depends(get_redis) 
):
    try:
        update_data = {k: v for k, v in datos.dict().items() if v is not None}
        if "codigo_cupon" in update_data:
            update_data["codigo_cupon"] = update_data["codigo_cupon"].upper().strip()
        if "fecha_inicio" in update_data:
            update_data["fecha_inicio"] = update_data["fecha_inicio"].isoformat()
        if "fecha_expiracion" in update_data:
            update_data["fecha_expiracion"] = update_data["fecha_expiracion"].isoformat()
        res = supabase_admin.table("cupones").update(update_data).eq("id", cupon_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Cupón no encontrado")
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            codigo = res.data[0].get("codigo_cupon", "Desconocido")
            notificar_administradores(
                tipo="sistema",
                titulo="Cupón Modificado",
                mensaje=f"{autor} ha editado las reglas del cupón '{codigo}'.",
                enlace="cupones.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:cupones_lista")
        return {"mensaje": "Cupón actualizado exitosamente", "data": res.data[0]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar el cupón: {str(e)}")

@router.put("/toggle-estado/{cupon_id}")
async def alternar_estado_cupon( 
    cupon_id: str,
    usuario_id: str = Depends(verificar_permiso("cupones_delete")),
    redis_client: Redis = Depends(get_redis) 
):
    try:
        cupon = supabase_admin.table("cupones").select("estado, codigo_cupon").eq("id", cupon_id).single().execute()
        if not cupon.data:
            raise HTTPException(status_code=404, detail="Cupón no encontrado")

        nuevo_estado = not cupon.data.get("estado", True)
        codigo_cupon = cupon.data.get("codigo_cupon", "Desconocido")
        res = supabase_admin.table("cupones").update({"estado": nuevo_estado}).eq("id", cupon_id).execute()
        
        try:
            autor = obtener_nombre_usuario(usuario_id)
            accion = "activado" if nuevo_estado else "desactivado"
            notificar_administradores(
                tipo="sistema",
                titulo=f"Cupón {accion.capitalize()}",
                mensaje=f"{autor} ha {accion} el cupón '{codigo_cupon}'.",
                enlace="cupones.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")
        
        await redis_client.delete("cache:admin:cupones_lista")
        return {"mensaje": "Estado de cupón actualizado", "nuevo_estado": nuevo_estado}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al cambiar el estado del cupón: {str(e)}")

@router.post("/validar", dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=60))])
async def validar_cupon_publico(datos: ValidarCuponRequest):
    try:
        codigo_clean = datos.codigo.upper().strip()
        res = supabase_admin.table("cupones").select("*").eq("codigo_cupon", codigo_clean).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="El código de cupón ingresado no existe.")
        
        cupon = res.data[0]
        
        if not cupon.get("estado", True):
            raise HTTPException(status_code=400, detail="Este cupón se encuentra inactivo.")
            
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        fecha_inicio = datetime.fromisoformat(cupon["fecha_inicio"].replace("Z", "+00:00")).replace(tzinfo=None)
        fecha_expiracion = datetime.fromisoformat(cupon["fecha_expiracion"].replace("Z", "+00:00")).replace(tzinfo=None)
        
        if ahora < fecha_inicio:
            raise HTTPException(status_code=400, detail="Este cupón aún no está disponible.")
            
        if ahora > fecha_expiracion:
            raise HTTPException(status_code=400, detail="Este cupón ha expirado.")
            
        limite_usos = cupon.get("limite_usos")
        usos_actuales = cupon.get("usos_actuales", 0)
        if limite_usos is not None and usos_actuales >= limite_usos:
            raise HTTPException(status_code=400, detail="Este cupón ha alcanzado su límite máximo de usos.")

        monto_minimo = float(cupon.get("monto_minimo") or 0.0)
        if datos.subtotal < monto_minimo:
            raise HTTPException(
                status_code=400, 
                detail=f"Este cupón requiere una compra mínima de S/ {monto_minimo:.2f}. Agrega más productos a tu carrito."
            )

        tipo = cupon.get("tipo_descuento")
        valor = float(cupon.get("valor_descuento") or 0.0)
        monto_descuento = 0.0
        
        if tipo in ["porcentaje", "percentage"]:
            monto_descuento = round((datos.subtotal * valor) / 100.0, 2)
        else: 
            monto_descuento = min(valor, datos.subtotal) 
        monto_descuento = round(monto_descuento, 2)
        total_final = round(max(0.0, datos.subtotal - monto_descuento), 2)
        
        return {
            "valido": True,
            "codigo": cupon["codigo_cupon"],
            "tipo_descuento": tipo,
            "valor_descuento": valor,
            "monto_descuento": monto_descuento,
            "total_final": total_final,
            "mensaje": f"¡Cupón {cupon['codigo_cupon']} aplicado con éxito!"
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al validar el cupón: {str(e)}")
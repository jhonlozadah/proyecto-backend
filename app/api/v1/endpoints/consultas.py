import json
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.email_brevo import enviar_correo_respuesta_consulta
from app.services.notificaciones_service import notificar_administradores
from app.api.dependencies import verificar_permiso, rate_limiter 
from redis.asyncio import Redis
from app.core.database import supabase_admin, get_redis

router = APIRouter()

def obtener_nombre_usuario(user_id: str) -> str:
    try:
        res = supabase_admin.table("usuarios").select("nombres, apellidos").eq("id", user_id).single().execute()
        if res.data:
            return f"{res.data.get('nombres', '')} {res.data.get('apellidos', '')}".strip()
    except Exception:
        pass
    return "Un administrador"

class EstadoConsultaUpdate(BaseModel):
    estado: str
    respuesta_email: Optional[str] = None

class ConsultaCreate(BaseModel):
    nombres: str
    apellidos: str
    email: EmailStr
    telefono: Optional[str] = None
    asunto: Optional[str] = None
    mensaje: str

@router.post("/", dependencies=[Depends(rate_limiter(max_requests=3, window_seconds=60))])
async def crear_consulta(
    consulta: ConsultaCreate,
    redis_client: Redis = Depends(get_redis) 
):
    try:
        id_usuario = None
        
        usuario_db = supabase_admin.table("usuarios").select("id").eq("correo", consulta.email).execute()
        if usuario_db.data:
            id_usuario = usuario_db.data[0]["id"]

        nueva_consulta = {
            "id_usuario": id_usuario,
            "nombres": consulta.nombres,
            "apellidos": consulta.apellidos,
            "email": consulta.email,
            "telefono": consulta.telefono,
            "asunto": consulta.asunto,
            "mensaje": consulta.mensaje
        }

        supabase_admin.table("consultas").insert(nueva_consulta).execute()
        
        try:
            asunto_texto = consulta.asunto if consulta.asunto else "Sin asunto"
            notificar_administradores(
                tipo="consulta",
                titulo="Nueva Consulta Recibida",
                mensaje=f"{consulta.nombres} {consulta.apellidos} ha enviado una consulta sobre: '{asunto_texto}'.",
                enlace="consultas.html" 
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] No se pudo alertar sobre la consulta: {e}")

        await redis_client.delete("cache:admin:consultas_lista")
        return {"mensaje": "Consulta enviada con éxito"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error al guardar la consulta: {e}")
        raise HTTPException(status_code=500, detail="Error interno al enviar la consulta.")

@router.get("/admin")
async def listar_consultas_admin(
    usuario_id: str = Depends(verificar_permiso("consultas_access")),
    redis_client: Redis = Depends(get_redis)
):
    cache_key = "cache:admin:consultas_lista"
    
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    try:
        response = supabase_admin.table("consultas").select("*").order("fecha_hora", desc=True).execute()
        if response.data:
            await redis_client.setex(cache_key, 900, json.dumps(response.data))
            
        return response.data
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error cargando consultas: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener las consultas.")

@router.put("/admin/{id_consulta}/estado")
async def actualizar_estado_consulta(
    id_consulta: str, 
    datos: EstadoConsultaUpdate, 
    usuario_id: str = Depends(verificar_permiso("consultas_access")),
    redis_client: Redis = Depends(get_redis)
):
    try:
        consulta_db = supabase_admin.table("consultas").select("email, nombres, asunto").eq("id", id_consulta).execute()
        if not consulta_db.data:
            raise HTTPException(status_code=404, detail="Consulta no encontrada")
            
        cliente = consulta_db.data[0]
        cliente_nombre = cliente.get("nombres", "un cliente")

        supabase_admin.table("consultas").update({"estado": datos.estado}).eq("id", id_consulta).execute()
        
        if datos.respuesta_email and datos.respuesta_email.strip():
            enviado = enviar_correo_respuesta_consulta(
                email_destino=cliente["email"],
                nombre_cliente=cliente["nombres"],
                asunto_original=cliente["asunto"],
                mensaje_respuesta=datos.respuesta_email.strip()
            )
            
            if not enviado:
                print("Advertencia: El correo se intentó enviar pero Brevo devolvió un error.")

        try:
            autor = obtener_nombre_usuario(usuario_id)
            if datos.respuesta_email and datos.respuesta_email.strip():
                mensaje_alerta = f"{autor} ha respondido y cambiado el estado de la consulta de {cliente_nombre} a '{datos.estado}'."
            else:
                mensaje_alerta = f"{autor} ha cambiado el estado de una consulta a '{datos.estado}'."
                
            notificar_administradores(
                tipo="sistema",
                titulo="Consulta Gestionada",
                mensaje=mensaje_alerta,
                enlace="consultas.html"
            )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN] {e}")

        await redis_client.delete("cache:admin:consultas_lista")
        return {"mensaje": "Estado actualizado y procesado correctamente"}
    except HTTPException as he:
        raise he    
    except Exception as e:
        print(f"Error actualizando consulta: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar el estado o procesar la respuesta.")
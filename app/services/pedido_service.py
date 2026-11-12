from app.core.database import supabase, supabase_admin
from app.schemas.pedido_schema import CrearPedidoRequest
from app.services.pasarela_pago import crear_preferencia_mp
from app.services.notificaciones_service import notificar_administradores
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi import HTTPException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def procesar_nueva_orden(datos: CrearPedidoRequest, token: str = None):
    user_id = None
    if token:
        try:
            user_response = supabase.auth.get_user(token)
            if user_response and user_response.user:
                user_id = user_response.user.id
        except Exception:
            pass

    datos_actualizar_usuario = {
        "nombres": datos.cliente.nombres,
        "apellidos": datos.cliente.apellidos,
        "telefono": datos.cliente.telefono,
        "tipo_documento": datos.cliente.tipo_documento,
        "numero_documento": datos.cliente.numero_documento,
        "departamento": datos.envio.departamento,
        "provincia": datos.envio.provincia,
        "distrito": datos.envio.distrito,
        "direccion": datos.envio.direccion,
        "referencia": datos.envio.referencia
    }
    
    datos_actualizar_usuario = {k: v for k, v in datos_actualizar_usuario.items() if v}
    correo_limpio = datos.cliente.correo.lower().strip()

    if not user_id:
        res_user = supabase_admin.table("usuarios").select("id").eq("correo", correo_limpio).execute()
        if res_user.data:
            user_id = res_user.data[0]["id"]
            if getattr(datos.cliente, "crear_cuenta", False):
                raise HTTPException(
                    status_code=400, 
                    detail="Este correo ya está registrado. Por favor, inicia sesión para comprar, o desmarca la opción de 'Crear cuenta' para comprar como invitado."
                )
            
            if datos_actualizar_usuario:
                supabase_admin.table("usuarios").update(datos_actualizar_usuario).eq("id", user_id).execute()
        else:
            rol_res = supabase_admin.table("roles").select("id").eq("nombre", "cliente").execute()
            id_rol = rol_res.data[0]["id"] if rol_res.data else None
            
            nuevo_user = {
                "correo": correo_limpio,
                "id_rol": id_rol,
                **datos_actualizar_usuario
            }
            
            if getattr(datos.cliente, "crear_cuenta", False) and getattr(datos.cliente, "contrasena", None):
                try:
                    auth_response = supabase_admin.auth.admin.create_user({
                        "email": correo_limpio,
                        "password": datos.cliente.contrasena,
                        "email_confirm": True
                    })
                    
                    nuevo_user["id"] = auth_response.user.id
                    nuevo_user["contrasena"] = get_password_hash(datos.cliente.contrasena)
                except Exception as e:
                    raise HTTPException(
                        status_code=400, 
                        detail="Hubo un problema al registrar tu cuenta en el sistema de seguridad. Intenta comprar como invitado."
                    )
                
            insert_user = supabase_admin.table("usuarios").insert(nuevo_user).execute()
            user_id = insert_user.data[0]["id"]
    else:
        if datos_actualizar_usuario:
            supabase_admin.table("usuarios").update(datos_actualizar_usuario).eq("id", user_id).execute()

    subtotal_real = 0.0
    detalles_pedido = []
    for item in datos.items:
        prod_res = supabase_admin.table("productos").select("nombre, precio_normal, precio_oferta, stock").eq("id", item.id_producto).single().execute()
        if not prod_res.data:
            raise ValueError(f"El producto con ID {item.id_producto} no existe.")

        prod = prod_res.data
        if prod["stock"] < item.cantidad:
            raise ValueError(f"Stock insuficiente para {prod['nombre']}.")
        
        nuevo_stock = prod["stock"] - item.cantidad
        supabase_admin.table("productos").update({"stock": nuevo_stock}).eq("id", item.id_producto).execute()
        
        try:
            umbral_minimo = 5
            if nuevo_stock == 0:
                notificar_administradores(
                    tipo="stock",
                    titulo="¡Producto Agotado!",
                    mensaje=f"El producto '{prod['nombre']}' se ha quedado sin unidades.",
                    enlace="productos.html"
                )
            elif nuevo_stock <= umbral_minimo:
                notificar_administradores(
                    tipo="stock",
                    titulo="Alerta de Stock Bajo",
                    mensaje=f"El producto '{prod['nombre']}' tiene ahora {nuevo_stock} unidades disponibles.",
                    enlace="productos.html" 
                )
        except Exception as e:
            print(f"[ERROR NOTIFICACIÓN STOCK] {e}")

        precio_base = prod["precio_oferta"] if (prod["precio_oferta"] and prod["precio_oferta"] < prod["precio_normal"]) else prod["precio_normal"]
        precio = float(precio_base)
        subtotal_item = precio * item.cantidad
        subtotal_real += subtotal_item
        detalles_pedido.append({
            "id_producto": item.id_producto,
            "nombre": prod["nombre"],
            "cantidad": item.cantidad,
            "precio_unitario": precio,
            "subtotal": subtotal_item
        })

    descuento = 0.0
    id_cupon = None
    if datos.codigo_cupon:
        cupon_res = supabase_admin.table("cupones").select("id, tipo_descuento, valor_descuento, monto_minimo").eq("codigo_cupon", datos.codigo_cupon.upper()).eq("estado", True).execute()
        if cupon_res.data:
            c = cupon_res.data[0]
            monto_min = float(c["monto_minimo"]) if c["monto_minimo"] else 0.0
            if subtotal_real >= monto_min:
                id_cupon = c["id"]
                val_desc = float(c["valor_descuento"])
                descuento = subtotal_real * (val_desc / 100.0) if c["tipo_descuento"] == "porcentaje" else val_desc

    items_mp = []
    factor_descuento = 1.0
    if descuento > 0 and subtotal_real > 0:
        factor_descuento = (subtotal_real - descuento) / subtotal_real

    for d in detalles_pedido:
        precio_con_descuento = d["precio_unitario"] * factor_descuento
        items_mp.append({
            "title": d["nombre"],
            "quantity": d["cantidad"],
            "unit_price": round(precio_con_descuento, 2), 
            "currency_id": "PEN"
        })
        del d["nombre"]

    costo_envio_num = float(datos.envio.costo_envio)
    total_final = max(0.0, (subtotal_real - descuento)) + costo_envio_num
    nuevo_pedido = {
        "id_cliente": user_id,
        "id_cupon": id_cupon,
        "total": total_final,
        "estado": "pendiente",
        "tipo_comprobante": datos.cliente.tipo_comprobante,
        "ruc_factura": datos.cliente.ruc_factura if datos.cliente.tipo_comprobante == "factura" else None,
        "razon_social_factura": datos.cliente.razon_social if datos.cliente.tipo_comprobante == "factura" else None,
        "metodo_despacho": datos.envio.metodo_despacho,
        "costo_envio": costo_envio_num,
        "fecha_recojo": datos.envio.fecha_recojo if datos.envio.fecha_recojo else None,
        "horario_recojo": datos.envio.horario_recojo,
        "receptor_tipo": datos.envio.receptor_tipo,
        "receptor_nombres": datos.envio.receptor_nombres,
        "receptor_documento_tipo": datos.envio.receptor_documento_tipo,
        "receptor_documento_num": datos.envio.receptor_documento_num,
        "receptor_celular": datos.envio.receptor_celular
    }

    pedido_creado = supabase_admin.table("pedidos").insert(nuevo_pedido).execute()
    id_pedido = pedido_creado.data[0]["id"]

    for d in detalles_pedido:
        d["id_pedido"] = id_pedido
    supabase_admin.table("detalle_pedido").insert(detalles_pedido).execute()
    
    try:
        notificar_administradores(
            tipo="pedido",
            titulo="Nuevo Pedido Recibido",
            mensaje=f"El cliente {datos.cliente.nombres} {datos.cliente.apellidos} ha realizado un pedido por S/ {total_final:.2f}.",
            enlace=f"detalle-pedido.html?id={id_pedido}"
        )
    except Exception as e:
        print(f"[ERROR NOTIFICACIÓN PEDIDO] {e}")
    
    cliente_dict = datos.cliente.model_dump()
    link_pago = crear_preferencia_mp(
        pedido_id=id_pedido,
        items_mp=items_mp,
        cliente=cliente_dict,
        costo_envio=costo_envio_num,
        metodo_pago=datos.metodo_pago
    )

    return link_pago

def limpiar_pedidos_abandonados():
    try:
        tiempo_limite = (datetime.utcnow() - timedelta(hours=1)).isoformat()

        res_pedidos = supabase_admin.table("pedidos") \
            .select("id") \
            .eq("estado", "pendiente") \
            .lte("fecha_hora_pedido", tiempo_limite) \
            .execute()

        if not res_pedidos.data:
            return

        pedidos_ids = [p["id"] for p in res_pedidos.data]
        res_detalles = supabase_admin.table("detalle_pedido") \
            .select("id_producto, cantidad") \
            .in_("id_pedido", pedidos_ids) \
            .execute()

        devoluciones = {}
        for detalle in res_detalles.data:
            pid = detalle["id_producto"]
            devoluciones[pid] = devoluciones.get(pid, 0) + detalle["cantidad"]

        for pid, cantidad_restaurar in devoluciones.items():
            prod_db = supabase_admin.table("productos").select("stock").eq("id", pid).single().execute()
            if prod_db.data:
                nuevo_stock = prod_db.data["stock"] + cantidad_restaurar
                supabase_admin.table("productos").update({"stock": nuevo_stock}).eq("id", pid).execute()

        for pid in pedidos_ids:
            supabase_admin.table("pedidos").update({"estado": "cancelado"}).eq("id", pid).execute()

        print(f"[SISTEMA] Autolimpieza ejecutada: {len(pedidos_ids)} pedidos cancelados, stock restaurado.")

    except Exception as e:
        print(f"[ERROR CRON] Error liberando stock: {e}")
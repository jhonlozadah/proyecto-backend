import os
import mercadopago
from app.core.config import settings

sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

def crear_preferencia_mp(
    pedido_id: str,
    items_mp: list,
    cliente: dict,
    costo_envio: float,
    metodo_pago: str,
    pedido_info: dict | None = None
):
    email_comprador = (cliente.get("correo") or "").strip()
    if not email_comprador:
        raise ValueError("El correo electrónico del comprador es obligatorio para procesar el pago.")

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "https://edificando.vercel.app/"
    ).strip().rstrip("/")

    URL_EDGE_FUNCTION = "https://gzcbcnkodzadxkkpsyrr.supabase.co/functions/v1/dynamic-handler"
    pedido_info = pedido_info or {}

    items_normalizados = []
    for idx, item in enumerate(items_mp, start=1):
        titulo = str(item.get("nombre") or item.get("title") or f"Producto Edificando {idx}")[:250]
        prod_id = str(item.get("sku") or item.get("id") or f"PROD-{idx}")
        descripcion = str(
            item.get("descripcion_corta")
            or item.get("description")
            or f"Material de construcción - {titulo}"
        )[:250]

        items_normalizados.append({
            "id": prod_id,
            "title": titulo,
            "description": descripcion,
            "category_id": "construction",
            "quantity": int(item.get("cantidad") or item.get("quantity") or 1),
            "currency_id": "PEN",
            "unit_price": round(float(item.get("precio_unitario") or item.get("unit_price") or 0), 2)
        })

    payer_data = {
        "name": (cliente.get("nombres") or "Cliente").strip(),
        "surname": (cliente.get("apellidos") or "Edificando").strip(),
        "email": email_comprador,
    }

    raw_tel = cliente.get("telefono") or pedido_info.get("receptor_celular") or ""
    telefono = "".join(filter(str.isdigit, str(raw_tel)))
    if telefono:
        payer_data["phone"] = {
            "area_code": "51",
            "number": telefono[-9:]
        }

    num_doc = str(
        cliente.get("numero_documento")
        or pedido_info.get("receptor_documento_num")
        or pedido_info.get("ruc_factura")
        or ""
    ).strip()

    tipo_doc = str(
        cliente.get("tipo_documento")
        or pedido_info.get("receptor_documento_tipo")
        or ("RUC" if len(num_doc) == 11 else "DNI")
    ).upper()

    if num_doc:
        payer_data["identification"] = {
            "type": tipo_doc if tipo_doc in ["DNI", "CE", "RUC"] else "Otro",
            "number": num_doc
        }

    if cliente.get("direccion"):
        payer_data["address"] = {
            "street_name": str(cliente.get("direccion"))[:250]
        }

    preference_data = {
        "items": items_normalizados,
        "payer": payer_data,
        "back_urls": {
            "success": f"{frontend_url}/main/index.html?estado=exito",
            "failure": f"{frontend_url}/main/index.html?estado=fallo",
            "pending": f"{frontend_url}/main/index.html?estado=pendiente"
        },
        "auto_return": "approved",
        "notification_url": URL_EDGE_FUNCTION,
        "external_reference": str(pedido_id),
        "statement_descriptor": "EDIFICANDO"
    }

    if metodo_pago == "yape":
        preference_data["payment_methods"] = {
            "default_payment_method_id": "yape"
        }

    if costo_envio > 0:
        preference_data["shipments"] = {
            "cost": float(costo_envio),
            "mode": "not_specified"
        }

    print(f"[DEBUG MP] Payer enviado: {payer_data}")

    resultado = sdk.preference().create(preference_data)
    if resultado["status"] >= 400:
        print(f"❌ Error Mercado Pago ({resultado['status']}): {resultado['response']}")
        raise ValueError(f"Error Mercado Pago: {resultado['response']}")

    res = resultado["response"]
    init_point = res.get("init_point")
    if not init_point:
        raise ValueError("Mercado Pago no devolvió una URL de pago de producción válida.")

    return init_point
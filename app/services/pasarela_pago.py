import os
import mercadopago
from app.core.config import settings

sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

def crear_preferencia_mp(pedido_id: str, items_mp: list, cliente: dict, costo_envio: float, metodo_pago: str):
    email_comprador = (cliente.get("correo") or "").strip()
    if not email_comprador:
        raise ValueError("El correo electrónico del comprador es obligatorio para procesar el pago.")

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "https://jaye-hypesthesic-dextrorsely.ngrok-free.dev"
    ).rstrip("/")

    URL_EDGE_FUNCTION = "https://gzcbcnkodzadxkkpsyrr.supabase.co/functions/v1/dynamic-handler"

    payer_data = {
        "name": cliente.get("nombres", "Cliente"),
        "surname": cliente.get("apellidos", "Edificando"),
        "email": email_comprador,
    }

    telefono = "".join(filter(str.isdigit, str(cliente.get("telefono") or "")))
    if telefono:
        payer_data["phone"] = {
            "area_code": "51",
            "number": telefono
        }

    num_doc = (cliente.get("numero_documento") or "").strip()
    tipo_doc = (cliente.get("tipo_documento") or "DNI").upper()
    if num_doc:
        payer_data["identification"] = {
            "type": tipo_doc if tipo_doc in ["DNI", "CE", "RUC"] else "Otro",
            "number": num_doc
        }

    preference_data = {
        "items": items_mp,
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

    resultado = sdk.preference().create(preference_data)
    if resultado["status"] >= 400:
        print(f"❌ Error Mercado Pago ({resultado['status']}): {resultado['response']}")
        raise ValueError(f"Error Mercado Pago: {resultado['response']}")

    res = resultado["response"]
    init_point = res.get("init_point")
    if not init_point:
        raise ValueError("Mercado Pago no devolvió una URL de pago de producción válida.")

    return init_point
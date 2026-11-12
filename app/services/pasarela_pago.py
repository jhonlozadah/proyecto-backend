import mercadopago
from app.core.config import settings

sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

def crear_preferencia_mp(pedido_id: str, items_mp: list, cliente: dict, costo_envio: float, metodo_pago: str):
    email_comprador = "test_user_7104209745891278445@testuser.com"
    URL_EDGE_FUNCTION = "https://gzcbcnkodzadxkkpsyrr.supabase.co/functions/v1/dynamic-handler"
    preference_data = {
        "items": items_mp,
        "payer": {
            "name": cliente.get("nombres", "Cliente"),
            "surname": cliente.get("apellidos", "Edificando"),
            "email": email_comprador
        },
        
        "back_urls": {
            "success": "https://127.0.0.1:5500/main/index.html?estado=exito",
            "failure": "https://127.0.0.1:5500/main/index.html?estado=fallo",
            "pending": "https://127.0.0.1:5500/main/index.html?estado=pendiente"
        },

        "auto_return": "approved",
        "notification_url": URL_EDGE_FUNCTION,
        "auto_return": "approved",
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
    return res.get("sandbox_init_point") or res.get("init_point")
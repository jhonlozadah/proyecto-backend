import requests
from app.core.config import settings

def enviar_correo_recuperacion(email_destino: str, codigo: str) -> bool:
    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json"
    }

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f6f8;
                    margin: 0;
                    padding: 40px 20px;
                    -webkit-font-smoothing: antialiased;
                }}
                .card {{
                    max-width: 500px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 12px;
                    padding: 32px;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                    text-align: center;
                }}
                .header {{
                    background-color: #1453a0;
                    color: #ffffff;
                    padding: 16px;
                    border-radius: 8px;
                    font-weight: 700;
                    font-size: 22px;
                    letter-spacing: 0.5px;
                    margin-bottom: 24px;
                }}
                .title {{
                    color: #0f172a;
                    margin-top: 0;
                    margin-bottom: 12px;
                    font-size: 20px;
                    font-weight: 600;
                }}
                .text {{
                    color: #334155;
                    font-size: 15px;
                    line-height: 1.5;
                    margin-bottom: 20px;
                }}
                .code-box {{
                    background-color: #f0f5fa;
                    border: 2px dashed #1453a0;
                    padding: 18px;
                    font-size: 32px;
                    font-weight: 800;
                    letter-spacing: 10px;
                    color: #1453a0;
                    margin: 24px 0;
                    border-radius: 8px;
                    display: inline-block;
                    width: 80%;
                }}
                .disclaimer {{
                    color: #64748b;
                    font-size: 13px;
                    line-height: 1.4;
                    margin-top: 20px;
                }}
                .footer {{
                    font-size: 12px;
                    color: #94a3b8;
                    margin-top: 28px;
                    border-top: 1px solid #f1f5f9;
                    padding-top: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">Edificando</div>
                <h2 class="title">Código de Verificación</h2>
                <p class="text">Has solicitado restablecer tu contraseña. Utiliza el siguiente código para completar la verificación:</p>
                <div class="code-box">{codigo}</div>
                <p class="disclaimer">Este código expira en 15 minutos. Si no solicitaste este cambio, puedes ignorar este correo de forma segura.</p>
                <div class="footer">&copy; Edificando. Todos los derechos reservados.</div>
            </div>
        </body>
    </html>
    """

    payload = {
        "sender": {
            "name": settings.SENDER_NAME,
            "email": settings.SENDER_EMAIL
        },
        "to": [
            {
                "email": email_destino
            }
        ],
        "subject": f"{codigo} es tu código de recuperación - Edificando",
        "htmlContent": html_content
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code >= 400:
        print(f"[ERROR BREVO API]: {response.text}")
        return False

    return True

def enviar_correo_estado_pedido(email_destino: str, nombre_cliente: str, pedido_id: str, nuevo_estado: str) -> bool:
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json"
    }

    id_corto = pedido_id[:8].upper()
    estado_normalizado = nuevo_estado.lower()
    mensajes = {
        "recibido": "Hemos recibido tu pedido y está en cola para ser procesado.",
        "procesando": "¡Buenas noticias! Estamos preparando tu pedido con mucho cuidado.",
        "enviado": "¡Tu pedido está en camino! Pronto llegará a su destino.",
        "completado": "Tu pedido ha sido entregado exitosamente. ¡Gracias por confiar en Edificando!",
        "cancelado": "Tu pedido ha sido cancelado. Si tienes alguna duda o crees que es un error, contáctanos.",
        "reembolsado": "Se ha procesado exitosamente el reembolso de tu pedido."
    }

    mensaje_cuerpo = mensajes.get(estado_normalizado, f"El estado de tu pedido se ha actualizado a: {nuevo_estado.capitalize()}")
    color_badge = "#1453a0" 
    if estado_normalizado in ["completado", "enviado"]:
        color_badge = "#16a34a"
    elif estado_normalizado in ["cancelado", "fallido"]:
        color_badge = "#dc2626"
    elif estado_normalizado == "procesando":
        color_badge = "#ca8a04"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f6f8;
                    margin: 0;
                    padding: 40px 20px;
                    -webkit-font-smoothing: antialiased;
                }}
                .card {{
                    max-width: 550px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 12px;
                    padding: 32px;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                }}
                .header {{
                    background-color: #1453a0;
                    color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    font-weight: 700;
                    font-size: 22px;
                    text-align: center;
                    letter-spacing: 0.5px;
                    margin-bottom: 24px;
                }}
                .title {{
                    color: #0f172a;
                    margin-top: 0;
                    margin-bottom: 12px;
                    font-size: 18px;
                    font-weight: 600;
                }}
                .text {{
                    color: #334155;
                    font-size: 15px;
                    line-height: 1.6;
                    margin-bottom: 24px;
                }}
                .status-box {{
                    background-color: #f8fafc;
                    border-left: 4px solid {color_badge};
                    padding: 16px 20px;
                    border-radius: 4px;
                    margin-bottom: 24px;
                }}
                .status-label {{
                    font-size: 12px;
                    text-transform: uppercase;
                    color: #64748b;
                    font-weight: bold;
                    letter-spacing: 1px;
                    margin-bottom: 4px;
                }}
                .status-value {{
                    font-size: 20px;
                    font-weight: 700;
                    color: {color_badge};
                    margin: 0;
                }}
                .footer {{
                    font-size: 12px;
                    color: #94a3b8;
                    margin-top: 32px;
                    border-top: 1px solid #f1f5f9;
                    padding-top: 16px;
                    text-align: center;
                }}
                .btn-track {{
                    display: inline-block;
                    background-color: #1453a0;
                    color: #ffffff;
                    text-decoration: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 14px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">EDIFICANDO</div>
                <h2 class="title">Hola, {nombre_cliente}</h2>
                <p class="text">Te escribimos para informarte que hay una actualización en tu pedido <strong>#PED-{id_corto}</strong>.</p>
                <div class="status-box">
                    <div class="status-label">Nuevo Estado del Pedido</div>
                    <p class="status-value">{nuevo_estado.upper()}</p>
                </div>
                <p class="text">{mensaje_cuerpo}</p>
                <p class="text">Puedes revisar el detalle completo de tus productos y el seguimiento ingresando a tu cuenta en nuestra tienda.</p>
                <div class="footer">
                    Este es un correo automático, por favor no respondas a esta dirección.<br>
                    &copy; Edificando. Todos los derechos reservados.
                </div>
            </div>
        </body>
    </html>
    """

    payload = {
        "sender": {
            "name": settings.SENDER_NAME,
            "email": settings.SENDER_EMAIL
        },
        "to": [
            {
                "email": email_destino,
                "name": nombre_cliente
            }
        ],
        "subject": f"Actualización de Pedido #PED-{id_corto} - Edificando",
        "htmlContent": html_content
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        print(f"[ERROR BREVO API - ESTADO PEDIDO]: {response.text}")
        return False

    return True

def enviar_correo_respuesta_consulta(email_destino: str, nombre_cliente: str, asunto_original: str, mensaje_respuesta: str) -> bool:
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json"
    }

    asunto_display = asunto_original if asunto_original else "tu consulta"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f6f8;
                    margin: 0;
                    padding: 40px 20px;
                    -webkit-font-smoothing: antialiased;
                }}
                .card {{
                    max-width: 550px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 12px;
                    padding: 32px;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                }}
                .header {{
                    background-color: #1453a0;
                    color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    font-weight: 700;
                    font-size: 22px;
                    text-align: center;
                    letter-spacing: 0.5px;
                    margin-bottom: 24px;
                }}
                .title {{
                    color: #0f172a;
                    margin-top: 0;
                    margin-bottom: 12px;
                    font-size: 18px;
                    font-weight: 600;
                }}
                .text {{
                    color: #334155;
                    font-size: 15px;
                    line-height: 1.6;
                    margin-bottom: 24px;
                }}
                .reply-box {{
                    background-color: #f0f5fa;
                    border-left: 4px solid #1453a0;
                    padding: 20px;
                    border-radius: 4px;
                    margin-bottom: 24px;
                    color: #1e293b;
                    font-size: 15px;
                    line-height: 1.6;
                    white-space: pre-wrap;
                }}
                .footer {{
                    font-size: 12px;
                    color: #94a3b8;
                    margin-top: 32px;
                    border-top: 1px solid #f1f5f9;
                    padding-top: 16px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">EDIFICANDO</div>
                <h2 class="title">Hola, {nombre_cliente}</h2>
                <p class="text">En respuesta a <strong>{asunto_display}</strong>, nuestro equipo se ha comunicado contigo:</p>
                
                <div class="reply-box">{mensaje_respuesta}</div>
                
                <p class="text">Si tienes alguna otra duda o necesitas mayor información, puedes responder directamente a este correo o contactarnos por WhatsApp.</p>
                <div class="footer">
                    &copy; Edificando. Todos los derechos reservados.
                </div>
            </div>
        </body>
    </html>
    """

    payload = {
        "sender": {
            "name": settings.SENDER_NAME,
            "email": settings.SENDER_EMAIL
        },
        "to": [
            {
                "email": email_destino,
                "name": nombre_cliente
            }
        ],
        "subject": f"Respuesta a tu consulta: {asunto_display} - Edificando",
        "htmlContent": html_content
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        print(f"[ERROR BREVO API - RESPUESTA CONSULTA]: {response.text}")
        return False

    return True
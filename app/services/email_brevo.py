import requests
from app.core.config import settings

LOGO_URL = "https://www.edificando.com.pe/img/logo.png"


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
        <title>Código de Verificación - Edificando</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <!-- Texto de vista previa oculto -->
        <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
            Tu código de seguridad es {codigo}. Expira en 15 minutos.
        </div>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9; padding: 40px 16px;">
            <tr>
                <td align="center">
                    <!-- Contenedor Principal -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 540px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.06);">
                        
                        <!-- Cabecera Corporativa -->
                        <tr>
                            <td align="center" style="background: linear-gradient(135deg, #1453a0 0%, #0d3b75 100%); background-color: #1453a0; padding: 32px 24px; border-bottom: 4px solid #2563eb;">
                                <img src="{LOGO_URL}" alt="EDIFICANDO" height="42" style="display: block; max-height: 42px; width: auto; border: 0; color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: 2px;">
                                <p style="margin: 8px 0 0 0; color: #bfdbfe; font-size: 11px; text-transform: uppercase; letter-spacing: 1.8px; font-weight: 600;">
                                    Seguridad de Cuenta
                                </p>
                            </td>
                        </tr>

                        <!-- Cuerpo del Mensaje -->
                        <tr>
                            <td style="padding: 40px 36px 32px 36px; text-align: center;">
                                <!-- Etiqueta Superior -->
                                <span style="display: inline-block; background-color: #eff6ff; color: #1453a0; font-size: 12px; font-weight: 700; padding: 6px 14px; border-radius: 999px; letter-spacing: 0.5px; margin-bottom: 16px;">
                                    RECUPERACIÓN DE CONTRASEÑA
                                </span>

                                <h1 style="margin: 0 0 12px 0; color: #0f172a; font-size: 24px; font-weight: 700; line-height: 1.3;">
                                    Código de Verificación
                                </h1>

                                <p style="margin: 0 0 28px 0; color: #475569; font-size: 15px; line-height: 1.6;">
                                    Has solicitado restablecer tu contraseña. Ingresa el siguiente código temporal en la pantalla de verificación para continuar:
                                </p>

                                <!-- Caja de Código OTP -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 24px;">
                                    <tr>
                                        <td align="center" style="background-color: #f8fafc; border: 2px dashed #1453a0; border-radius: 12px; padding: 24px 16px;">
                                            <div style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 800; letter-spacing: 12px; color: #1453a0; padding-left: 12px;">
                                                {codigo}
                                            </div>
                                        </td>
                                    </tr>
                                </table>

                                <!-- Indicador de Expiración -->
                                <p style="margin: 0 0 28px 0; color: #64748b; font-size: 13px;">
                                    Este código es de un solo uso y expirará en <strong style="color: #0f172a;">15 minutos</strong>.
                                </p>

                                <!-- Aviso de Seguridad -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td style="background-color: #f8fafc; border-left: 3px solid #94a3b8; border-radius: 6px; padding: 14px 16px; text-align: left;">
                                            <p style="margin: 0; color: #64748b; font-size: 12.5px; line-height: 1.5;">
                                                <strong style="color: #334155;">¿No solicitaste este cambio?</strong><br>
                                                Si no fuiste tú, ignora este mensaje. Tu contraseña actual permanecerá protegida y sin modificaciones.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Pie de Página -->
                        <tr>
                            <td style="background-color: #f8fafc; padding: 24px 36px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="margin: 0 0 6px 0; color: #64748b; font-size: 12px;">
                                    Este es un mensaje automático de seguridad, por favor no respondas a este correo.
                                </p>
                                <p style="margin: 0; color: #94a3b8; font-size: 12px; font-weight: 500;">
                                    &copy; Edificando. Todos los derechos reservados.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
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
    bg_badge = "#eff6ff"
    if estado_normalizado in ["completado", "enviado"]:
        color_badge = "#16a34a"
        bg_badge = "#f0fdf4"
    elif estado_normalizado in ["cancelado", "fallido"]:
        color_badge = "#dc2626"
        bg_badge = "#fef2f2"
    elif estado_normalizado == "procesando":
        color_badge = "#ca8a04"
        bg_badge = "#fefce8"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Actualización de Pedido #PED-{id_corto} - Edificando</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
            Tu pedido #PED-{id_corto} ahora se encuentra en estado: {nuevo_estado.upper()}.
        </div>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9; padding: 40px 16px;">
            <tr>
                <td align="center">
                    <!-- Contenedor Principal -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.06);">
                        
                        <!-- Cabecera Corporativa -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #1453a0 0%, #0d3b75 100%); background-color: #1453a0; padding: 28px 36px; border-bottom: 4px solid #2563eb;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td align="left" valign="middle">
                                            <img src="{LOGO_URL}" alt="EDIFICANDO" height="38" style="display: block; max-height: 38px; width: auto; border: 0; color: #ffffff; font-size: 22px; font-weight: 800; letter-spacing: 1.5px;">
                                        </td>
                                        <td align="right" valign="middle">
                                            <span style="display: inline-block; background-color: rgba(255, 255, 255, 0.15); color: #ffffff; font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 6px; letter-spacing: 0.8px;">
                                                #PED-{id_corto}
                                            </span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Cuerpo del Mensaje -->
                        <tr>
                            <td style="padding: 36px 36px 32px 36px; text-align: left;">
                                <h1 style="margin: 0 0 12px 0; color: #0f172a; font-size: 22px; font-weight: 700;">
                                    Hola, {nombre_cliente}
                                </h1>

                                <p style="margin: 0 0 24px 0; color: #475569; font-size: 15px; line-height: 1.6;">
                                    Te escribimos para informarte que hay una actualización en el estado de tu orden <strong style="color: #0f172a;">#PED-{id_corto}</strong>:
                                </p>

                                <!-- Tarjeta de Estado -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 24px;">
                                    <tr>
                                        <td style="background-color: {bg_badge}; border: 1px solid #e2e8f0; border-left: 5px solid {color_badge}; border-radius: 10px; padding: 20px 24px;">
                                            <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; letter-spacing: 1.2px; margin-bottom: 6px;">
                                                Nuevo Estado del Pedido
                                            </div>
                                            <div style="font-size: 22px; font-weight: 800; color: {color_badge}; letter-spacing: 0.5px;">
                                                {nuevo_estado.upper()}
                                            </div>
                                        </td>
                                    </tr>
                                </table>

                                <p style="margin: 0 0 20px 0; color: #1e293b; font-size: 15px; font-weight: 500; line-height: 1.6;">
                                    {mensaje_cuerpo}
                                </p>

                                <p style="margin: 0; color: #64748b; font-size: 14px; line-height: 1.6;">
                                    Puedes revisar el detalle completo de tus productos y el historial de seguimiento ingresando a tu cuenta en nuestra tienda virtual.
                                </p>
                            </td>
                        </tr>

                        <!-- Pie de Página -->
                        <tr>
                            <td style="background-color: #f8fafc; padding: 24px 36px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="margin: 0 0 6px 0; color: #64748b; font-size: 12px;">
                                    Este es un correo automático, por favor no respondas a esta dirección.
                                </p>
                                <p style="margin: 0; color: #94a3b8; font-size: 12px; font-weight: 500;">
                                    &copy; Edificando. Todos los derechos reservados.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
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
        <title>Respuesta a tu consulta - Edificando</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
            Nuestro equipo de atención al cliente ha respondido a: {asunto_display}
        </div>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9; padding: 40px 16px;">
            <tr>
                <td align="center">
                    <!-- Contenedor Principal -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.06);">
                        
                        <!-- Cabecera Corporativa -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #1453a0 0%, #0d3b75 100%); background-color: #1453a0; padding: 28px 36px; border-bottom: 4px solid #2563eb;">
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td align="left" valign="middle">
                                            <img src="{LOGO_URL}" alt="EDIFICANDO" height="38" style="display: block; max-height: 38px; width: auto; border: 0; color: #ffffff; font-size: 22px; font-weight: 800; letter-spacing: 1.5px;">
                                        </td>
                                        <td align="right" valign="middle">
                                            <span style="display: inline-block; background-color: rgba(255, 255, 255, 0.15); color: #ffffff; font-size: 11px; font-weight: 700; padding: 6px 12px; border-radius: 999px; letter-spacing: 1px; text-transform: uppercase;">
                                                Atención al Cliente
                                            </span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Cuerpo del Mensaje -->
                        <tr>
                            <td style="padding: 36px 36px 32px 36px; text-align: left;">
                                <h1 style="margin: 0 0 12px 0; color: #0f172a; font-size: 22px; font-weight: 700;">
                                    Hola, {nombre_cliente}
                                </h1>

                                <p style="margin: 0 0 22px 0; color: #475569; font-size: 15px; line-height: 1.6;">
                                    En referencia a <strong style="color: #1453a0;">{asunto_display}</strong>, nuestro equipo te brinda la siguiente respuesta:
                                </p>

                                <!-- Caja de Respuesta del Asesor -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 24px;">
                                    <tr>
                                        <td style="background-color: #f8fafc; border: 1px solid #dbeafe; border-left: 5px solid #1453a0; border-radius: 10px; padding: 22px 24px;">
                                            <div style="font-size: 11px; text-transform: uppercase; color: #1453a0; font-weight: 700; letter-spacing: 1px; margin-bottom: 10px;">
                                                Mensaje de Soporte &bull; Edificando
                                            </div>
                                            <div style="color: #1e293b; font-size: 15px; line-height: 1.65; white-space: pre-wrap;">{mensaje_respuesta}</div>
                                        </td>
                                    </tr>
                                </table>

                                <!-- Nota de Contacto -->
                                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                    <tr>
                                        <td style="background-color: #eff6ff; border-radius: 8px; padding: 14px 18px;">
                                            <p style="margin: 0; color: #1e3a8a; font-size: 13.5px; line-height: 1.5;">
                                                Si tienes alguna otra consulta o requieres asesoría técnica adicional, puedes responder directamente a este correo o escribirnos por WhatsApp.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Pie de Página -->
                        <tr>
                            <td style="background-color: #f8fafc; padding: 24px 36px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="margin: 0 0 6px 0; color: #64748b; font-size: 12px;">
                                    Gracias por comunicarte con nosotros.
                                </p>
                                <p style="margin: 0; color: #94a3b8; font-size: 12px; font-weight: 500;">
                                    &copy; Edificando. Todos los derechos reservados.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
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
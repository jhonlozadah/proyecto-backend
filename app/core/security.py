import json
import base64
from app.core.config import settings

def decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        
        payload_b64 = parts[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        
        return json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception as e:
        print(f"[SECURITY] Error al decodificar JWT: {e}")
        return {}

# NOTA PARA EL FUTURO:
# Si decides validar la FIRMA criptográfica matemáticamente usando la JWT_SECRET_KEY 
# en lugar de consultar a Supabase en cada petición, aquí es donde usarías librerías 
# como 'PyJWT' o 'python-jose' con una función como esta:
#
# import jwt
# def verificar_firma_jwt(token: str):
#     return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"], audience="authenticated")
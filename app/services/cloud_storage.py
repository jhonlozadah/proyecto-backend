import cloudinary
import cloudinary.uploader
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

def subir_imagen(archivo_bytes: bytes, carpeta: str = "edificando/perfiles") -> str:
    respuesta = cloudinary.uploader.upload(archivo_bytes, folder=carpeta)
    return respuesta.get("secure_url")
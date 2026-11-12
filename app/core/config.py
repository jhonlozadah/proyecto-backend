from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    RECAPTCHA_SECRET_KEY: str 
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    BREVO_API_KEY: str
    SENDER_EMAIL: str
    SENDER_NAME: str
    SUPABASE_SERVICE_ROLE_KEY: str
    MERCADOPAGO_ACCESS_TOKEN: str
    JWT_SECRET_KEY: str
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://127.0.0.1:5500"
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500"
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import redis.asyncio as aioredis
from app.api.v1.router import api_router
from app.services.pedido_service import limpiar_pedidos_abandonados
from app.core.config import settings
import app.core.database as db

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.redis_pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL, 
        decode_responses=True,
        max_connections=10 
    )
    print("[SISTEMA] Pool de Redis inicializado correctamente.")

    scheduler = BackgroundScheduler()
    scheduler.add_job(limpiar_pedidos_abandonados, 'interval', minutes=60)
    scheduler.start()
    print("[SISTEMA] Tareas en segundo plano iniciadas correctamente.")
    
    yield 
    
    scheduler.shutdown()
    print("[SISTEMA] Tareas en segundo plano detenidas.")
    
    if db.redis_pool:
        await db.redis_pool.disconnect()
        print("[SISTEMA] Pool de Redis cerrado y recursos liberados.")

app = FastAPI(title="Edificando", lifespan=lifespan)

# Limpia espacios y barras finales (/) automáticamente
origenes_permitidos = [
    origen.strip().rstrip("/") 
    for origen in settings.CORS_ORIGINS.split(",") 
    if origen.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
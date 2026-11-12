import redis.asyncio as aioredis
from supabase import create_client, Client
from app.core.config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

redis_pool = None

async def get_redis() -> aioredis.Redis:
    if not redis_pool:
        raise Exception("El Pool de Redis no ha sido inicializado.")
    return aioredis.Redis(connection_pool=redis_pool)
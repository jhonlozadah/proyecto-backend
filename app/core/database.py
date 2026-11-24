import httpx
import redis.asyncio as aioredis
from supabase import create_client, Client
from app.core.config import settings

def _crear_http_client() -> httpx.Client:
    transport = httpx.HTTPTransport(http2=False, retries=2)
    return httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=15,
            max_connections=30,
            keepalive_expiry=30.0,
        ),
    )

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
supabase.postgrest.session = _crear_http_client()

supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
supabase_admin.postgrest.session = _crear_http_client()

def crear_cliente_auth() -> Client:
    cliente = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    cliente.postgrest.session = _crear_http_client()
    return cliente

redis_pool: aioredis.ConnectionPool | None = None
_redis_client: aioredis.Redis | None = None

def init_redis_pool(redis_url: str) -> aioredis.ConnectionPool:
    global redis_pool, _redis_client
    redis_pool = aioredis.ConnectionPool.from_url(
        redis_url,
        max_connections=15,        
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        health_check_interval=30,  
        decode_responses=True,
    )
    _redis_client = aioredis.Redis(connection_pool=redis_pool)
    return redis_pool

async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if redis_pool is not None:
        _redis_client = aioredis.Redis(connection_pool=redis_pool)
        return _redis_client

    init_redis_pool(settings.REDIS_URL)
    return _redis_client
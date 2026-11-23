import httpx
import redis.asyncio as aioredis
from supabase import create_client, Client
from app.core.config import settings

def _crear_http_client() -> httpx.Client:
    transport = httpx.HTTPTransport(http2=False, retries=2)
    return httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(20.0, connect=10.0),
        limits=httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
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

redis_pool = None

async def get_redis() -> aioredis.Redis:
    if not redis_pool:
        raise Exception("El Pool de Redis no ha sido inicializado.")
    return aioredis.Redis(connection_pool=redis_pool)
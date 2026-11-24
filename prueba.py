import os
import json
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

TABLAS = ["usuarios", "categorias", "productos", "cupones", "pedidos", "detalle_pedido"]

def formatear_valor(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float, Decimal)):
        return str(val)
    if isinstance(val, (dict, list)):
        texto = json.dumps(val, ensure_ascii=False).replace("'", "''")
        return f"'{texto}'::jsonb"
    texto = str(val).replace("'", "''")
    return f"'{texto}'"

with open("respaldo_datos.sql", "w", encoding="utf-8") as f:
    f.write("-- Respaldo de datos Edificando\n\n")
    for tabla in TABLAS:
        try:
            res = supabase.table(tabla).select("*").execute()
            filas = res.data or []
            if not filas:
                continue
            f.write(f"-- Tabla: {tabla} ({len(filas)} registros)\n")
            columnas = list(filas[0].keys())
            cols_str = ", ".join(f'"{c}"' for c in columnas)
            for fila in filas:
                vals_str = ", ".join(formatear_valor(fila.get(c)) for c in columnas)
                f.write(f'INSERT INTO public."{tabla}" ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n')
            f.write("\n")
            print(f"Exportada tabla {tabla}: {len(filas)} filas")
        except Exception as e:
            print(f"Omitida {tabla}: {e}")

print("Listo -> respaldo_datos.sql generado.")
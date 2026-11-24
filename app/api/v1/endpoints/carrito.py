import asyncio
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from app.core.database import supabase
from app.api.dependencies import obtener_usuario_actual, rate_limiter

router = APIRouter()

# Evita condiciones de carrera cuando un mismo usuario envía múltiples clics simultáneos
_user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _construir_respuesta_carrito(uid: str) -> dict:
    respuesta = supabase.table("carrito").select(
        "id, id_producto, cantidad, productos(nombre, precio_normal, precio_oferta, imagen_principal, stock)"
    ).eq("id_usuario", uid).order("creado_en").execute()

    items = []
    total = 0.0

    for c in (respuesta.data or []):
        prod = c.get("productos") or {}
        if isinstance(prod, list):
            prod = prod[0] if prod else {}

        precio_final = prod.get("precio_oferta") or prod.get("precio_normal") or 0
        cantidad = int(c["cantidad"])
        subtotal = float(precio_final) * cantidad
        total += subtotal

        items.append({
            "id_producto": c["id_producto"],
            "nombre": prod.get("nombre"),
            "precio": float(precio_final),
            "cantidad": cantidad,
            "stock_max": int(prod.get("stock") or 0),
            "imagen": prod.get("imagen_principal") or "src/images/products/default.png",
            "subtotal": subtotal
        })

    return {
        "items": items,
        "total": total,
        "cantidad_total": sum(i["cantidad"] for i in items)
    }


@router.get("/")
def obtener_carrito(usuario=Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    return _construir_respuesta_carrito(uid)


@router.post("/agregar", dependencies=[Depends(rate_limiter(max_requests=40, window_seconds=10))])
async def agregar_al_carrito(datos: dict, usuario=Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    id_prod = datos.get("id_producto")
    cantidad_agregada = int(datos.get("cantidad", 1))

    if cantidad_agregada < 1:
        raise HTTPException(status_code=400, detail="La cantidad debe ser al menos 1.")

    async with _user_locks[uid]:
        prod_res = supabase.table("productos").select("stock, nombre").eq("id", id_prod).execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail="El producto no existe.")

        stock_disponible = int(prod_res.data[0].get("stock") or 0)
        if stock_disponible <= 0:
            raise HTTPException(status_code=400, detail="Este producto se encuentra agotado.")

        existe = supabase.table("carrito").select("id, cantidad").eq("id_usuario", uid).eq("id_producto", id_prod).execute()
        cantidad_actual = int(existe.data[0]["cantidad"]) if existe.data else 0
        nueva_cant = cantidad_actual + cantidad_agregada

        if nueva_cant > stock_disponible:
            if cantidad_actual >= stock_disponible:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ya tienes el máximo disponible ({stock_disponible} und.) en tu carrito."
                )
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente. Solo quedan {stock_disponible} unidades disponibles."
            )

        if existe.data:
            supabase.table("carrito").update({"cantidad": nueva_cant}).eq("id", existe.data[0]["id"]).execute()
        else:
            supabase.table("carrito").insert({
                "id_usuario": uid,
                "id_producto": id_prod,
                "cantidad": cantidad_agregada
            }).execute()

        carrito_actualizado = _construir_respuesta_carrito(uid)
        return {"mensaje": "Producto agregado", **carrito_actualizado}


@router.put("/actualizar", dependencies=[Depends(rate_limiter(max_requests=40, window_seconds=10))])
async def actualizar_cantidad(datos: dict, usuario=Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    id_prod = datos.get("id_producto")
    nueva_cantidad = int(datos.get("cantidad", 1))

    if nueva_cantidad < 1:
        raise HTTPException(status_code=400, detail="La cantidad mínima permitida es 1.")

    async with _user_locks[uid]:
        prod_res = supabase.table("productos").select("stock").eq("id", id_prod).execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail="El producto no existe.")

        stock_disponible = int(prod_res.data[0].get("stock") or 0)
        if stock_disponible <= 0:
            raise HTTPException(status_code=400, detail="Este producto se encuentra agotado.")

        if nueva_cantidad > stock_disponible:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente. Solo quedan {stock_disponible} unidades disponibles."
            )

        supabase.table("carrito").update({"cantidad": nueva_cantidad}).eq("id_usuario", uid).eq("id_producto", id_prod).execute()

        carrito_actualizado = _construir_respuesta_carrito(uid)
        return {"mensaje": "Cantidad actualizada", **carrito_actualizado}


@router.delete("/{id_producto}", dependencies=[Depends(rate_limiter(max_requests=40, window_seconds=10))])
async def eliminar_del_carrito(id_producto: str, usuario=Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))

    async with _user_locks[uid]:
        supabase.table("carrito").delete().eq("id_usuario", uid).eq("id_producto", id_producto).execute()
        carrito_actualizado = _construir_respuesta_carrito(uid)
        return {"mensaje": "Producto eliminado", **carrito_actualizado}
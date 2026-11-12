from fastapi import APIRouter, Depends, HTTPException
from app.core.database import supabase
from app.api.dependencies import obtener_usuario_actual, rate_limiter

router = APIRouter()

@router.get("/")
def obtener_carrito(usuario = Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    respuesta = supabase.table("carrito").select(
        "id, id_producto, cantidad, productos(nombre, precio_normal, precio_oferta, imagen_principal, stock)"
    ).eq("id_usuario", uid).order("creado_en").execute()

    items = []
    total = 0

    for c in respuesta.data:
        prod = c.get("productos", {})
        if isinstance(prod, list) and prod: prod = prod[0]
        
        precio_final = prod.get("precio_oferta") or prod.get("precio_normal", 0)
        subtotal = float(precio_final) * int(c["cantidad"])
        total += subtotal
        
        items.append({
            "id_producto": c["id_producto"],
            "nombre": prod.get("nombre"),
            "precio": float(precio_final),
            "cantidad": c["cantidad"],
            "stock_max": prod.get("stock", 0),
            "imagen": prod.get("imagen_principal") or "src/images/products/default.png",
            "subtotal": subtotal
        })
    return {"items": items, "total": total, "cantidad_total": sum(i["cantidad"] for i in items)}

@router.post("/agregar", dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=10))])
def agregar_al_carrito(datos: dict, usuario = Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    id_prod = datos.get("id_producto")
    cantidad_agregada = int(datos.get("cantidad", 1))
    existe = supabase.table("carrito").select("id, cantidad").eq("id_usuario", uid).eq("id_producto", id_prod).execute()
    if existe.data:
        nueva_cant = existe.data[0]["cantidad"] + cantidad_agregada
        supabase.table("carrito").update({"cantidad": nueva_cant}).eq("id", existe.data[0]["id"]).execute()
    else:
        supabase.table("carrito").insert({"id_usuario": uid, "id_producto": id_prod, "cantidad": cantidad_agregada}).execute()
    return {"mensaje": "Producto agregado"}

@router.put("/actualizar", dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=10))])
def actualizar_cantidad(datos: dict, usuario = Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    supabase.table("carrito").update({"cantidad": int(datos.get("cantidad"))}).eq("id_usuario", uid).eq("id_producto", datos.get("id_producto")).execute()
    return {"mensaje": "Cantidad actualizada"}

@router.delete("/{id_producto}", dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=10))])
def eliminar_del_carrito(id_producto: str, usuario = Depends(obtener_usuario_actual)):
    uid = usuario.get("id") if isinstance(usuario, dict) else getattr(usuario, "id", str(usuario))
    supabase.table("carrito").delete().eq("id_usuario", uid).eq("id_producto", id_producto).execute()
    return {"mensaje": "Producto eliminado"}
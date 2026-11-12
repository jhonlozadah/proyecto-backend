from app.core.database import supabase_admin

def notificar_administradores(tipo: str, titulo: str, mensaje: str, enlace: str = None):
    try:
        roles = supabase_admin.table("roles").select("id").in_("nombre", ["administrador", "admin"]).execute()
        if not roles.data:
            return
            
        ids_roles = [r["id"] for r in roles.data]
        admins = supabase_admin.table("usuarios").select("id").in_("id_rol", ids_roles).execute()
        if not admins.data:
            return

        nuevas_notificaciones = []
        for admin in admins.data:
            nuevas_notificaciones.append({
                "id_usuario": admin["id"],
                "tipo": tipo,
                "titulo": titulo,
                "mensaje": mensaje,
                "enlace": enlace
            })
        if nuevas_notificaciones:
            supabase_admin.table("notificaciones").insert(nuevas_notificaciones).execute()
            
    except Exception as e:
        print(f"[ERROR NOTIFICACIONES] No se pudo enviar la alerta: {str(e)}")
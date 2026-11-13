<div align="center">
  <h1>🏗️ Edificando — E-Commerce Backend API</h1>
  <p>
    <strong>API RESTful de alto rendimiento, segura y escalable para la plataforma de comercio electrónico Edificando.</strong>
  </p>

  <p>
    <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
    <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
    <img src="https://img.shields.io/badge/Mercado_Pago-009EE3?style=for-the-badge&logo=mercadopago&logoColor=white" alt="Mercado Pago" />
  </p>
</div>

---

## 📋 Descripción General

Este repositorio contiene el núcleo backend de **Edificando**, diseñado bajo una arquitectura modular en **FastAPI**. El sistema gestiona tanto la experiencia de compra del cliente final (catálogo dinámico, búsqueda avanzada, carrito persistente, lista de deseos, reseñas y pagos en línea) como un completo **Panel Administrativo** con analíticas, reportes, gestión de inventario y control de acceso granular.

---

## ✨ Características Principales y Arquitectura

### ⚡ Rendimiento y Caché Distribuida (Redis)
* **Patrón Cache-Aside:** Implementación asíncrona (`redis.asyncio`) en rutas críticas de lectura pública (catálogo, productos recientes, top ventas, marcas, diseños/banners y blogs) y vistas administrativas, reduciendo la latencia de respuesta a milisegundos.
* **Invalidación Inteligente:** Limpieza automática y sincronizada de claves de caché (`cache:*`) ante cualquier operación de escritura (`POST`, `PUT`, `PATCH`, `DELETE`), garantizando consistencia de datos en tiempo real entre el panel de administración y la tienda.

### 🛡️ Seguridad y Control de Acceso (RBAC + MFA)
* **Control de Acceso Basado en Roles (RBAC):** Sistema dinámico de permisos granulares (`productos_access`, `usuarios_create`, `roles_edit`, `resenas_access`, etc.) validados mediante dependencias inyectables en FastAPI.
* **Autenticación Robusta:** Integración con **Supabase Auth** (soporte para correo/contraseña y OAuth con Google), manejo de sesiones mediante cookies `HttpOnly` y soporte nativo para **Autenticación Multifactor (MFA / TOTP)**.
* **Rate Limiting:** Protección contra ataques de fuerza bruta, scraping y spam mediante limitadores de tasa configurables por endpoint (ej. bloqueo estricto en endpoints de contraseñas, MFA y creación de reseñas).

### 💳 Integraciones de Terceros
* **Pasarela de Pagos:** Integración completa con **Mercado Pago (Checkout Pro)** para procesamiento de pagos seguros y confirmación automática de órdenes.
* **Notificaciones Transaccionales:** Envío automatizado de correos electrónicos mediante **Brevo** y sistema interno de alertas en tiempo real para administradores.
* **Almacenamiento en la Nube:** Gestión y optimización de recursos multimedia (imágenes de productos, banners, avatares y fichas técnicas).

---

## 📂 Estructura del Proyecto

```text
edificando-backend/
├── app/
│   ├── api/
│   │   ├── dependencies.py          # Middlewares de autenticación, RBAC y Rate Limiter
│   │   └── v1/
│   │       ├── router.py            # Enrutador principal de la API v1
│   │       └── endpoints/           # Controladores agrupados por dominio
│   │           ├── admin_dashboard.py
│   │           ├── admin_pedidos.py
│   │           ├── admin_reportes.py
│   │           ├── admin_ventas.py
│   │           ├── auth.py          # Login, registro, OAuth y gestión de sesión
│   │           ├── blogs.py         # Artículos y comentarios
│   │           ├── carrito.py       # Gestión del carrito de compras
│   │           ├── categorias.py    # Gestión de categorías
│   │           ├── consultas.py     # Formulario de contacto y soporte
│   │           ├── cupones.py       # Códigos de descuento y promociones
│   │           ├── disenos.py       # Banners, sliders y recursos visuales
│   │           ├── marcas.py        # Gestión de marcas asociadas
│   │           ├── notificaciones.py# Alertas en tiempo real del panel admin
│   │           ├── pedidos.py       # Creación y seguimiento de órdenes
│   │           ├── productos.py     # Catálogo, búsqueda, filtros y reseñas
│   │           ├── roles.py         # Gestión dinámica de roles y permisos
│   │           └── usuarios.py      # Perfil, MFA, lista de deseos y gestión admin
│   ├── core/
│   │   ├── config.py                # Variables de entorno y configuración global
│   │   ├── database.py              # Clientes de Supabase (público/admin) y Redis
│   │   └── security.py              # Utilidades criptográficas y validación de tokens
│   ├── schemas/                     # Modelos Pydantic para validación de entrada/salida
│   │   ├── auth_schema.py
│   │   ├── blog_schema.py
│   │   ├── categoria_schema.py
│   │   ├── cupon_schema.py
│   │   ├── marca_schema.py
│   │   ├── pedido_schema.py
│   │   ├── producto_schema.py
│   │   ├── roles_schema.py
│   │   └── usuario_schema.py
│   ├── services/                    # Lógica de negocio e integraciones externas
│   │   ├── carrito_service.py
│   │   ├── cloud_storage.py
│   │   ├── email_brevo.py
│   │   ├── notificaciones_service.py
│   │   ├── pasarela_pago.py
│   │   └── pedido_service.py
│   ├── utils/
│   │   └── formatters.py            # Helpers de formateo de datos y slugs
│   └── main.py                      # Punto de entrada de la aplicación FastAPI
├── .env                             # Variables de entorno
├── .gitignore
├── README.md
└── requeriments.txt                 # Dependencias del proyecto
```

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar el repositorio
```bash
git clone https://github.com/jhonlozadah/proyecto-backend.git
cd edificando-backend
```

### 2. Crear y activar el entorno virtual
```bash
# En Windows
python -m venv venv
venv\Scripts\activate

# En Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requeriments.txt
```

### 4. Configurar variables de entorno
Crea un archivo `.env` en la raíz del proyecto basándote en la siguiente plantilla:

```env
# Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu_anon_public_key
SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key

# Redis
REDIS_URL=redis://localhost:6379/0

# Mercado Pago
MERCADOPAGO_ACCESS_TOKEN=TEST-tu-token-de-acceso

# Brevo (Email)
BREVO_API_KEY=tu_api_key_de_brevo
SENDER_EMAIL=noreply@edificando.com

# Seguridad & CORS
FRONTEND_URL=http://127.0.0.1:5500
```

### 5. Ejecutar el servidor de desarrollo
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Una vez iniciado, podrás acceder a la documentación interactiva generada automáticamente por FastAPI:
* **Swagger UI:** `http://127.0.0.1:8000/docs`
* **ReDoc:** `http://127.0.0.1:8000/redoc`

---

## 📌 Módulos Principales de la API (`/api/v1`)

| Prefijo | Descripción | Seguridad / Optimización |
| :--- | :--- | :--- |
| `/auth` | Inicio de sesión, registro, refresh tokens y OAuth. | Cookies `HttpOnly` + Rate Limit |
| `/productos` | Catálogo público, filtros, detalles por slug y reseñas. | Caché Redis + Rate Limit |
| `/usuarios` | Perfil de cliente, lista de deseos, MFA y CRUD admin. | Caché aislada por usuario + RBAC |
| `/roles` | Administración de roles y matriz de permisos. | Caché Redis + RBAC estricto |
| `/pedidos` | Procesamiento de compras y webhooks de pago. | Integración Mercado Pago + Brevo |
| `/marcas` & `/categorias` | Taxonomía del catálogo de productos. | Caché Redis + Invalidación automática |
| `/disenos` | Gestión de banners y sliders dinámicos de la tienda. | Caché Redis (TTL 30m) |
| `/notificaciones` | Centro de alertas en tiempo real para el equipo admin. | Caché corta (TTL 60s) por usuario |

---

<div align="center">
  <p>Desarrollado con ❤️ para <strong>Edificando</strong>.</p>
</div>

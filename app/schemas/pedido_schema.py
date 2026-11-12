from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from decimal import Decimal

class ClienteCheckout(BaseModel):
    nombres: str = Field(..., min_length=1)
    apellidos: str = Field(..., min_length=1)
    correo: EmailStr
    telefono: str
    tipo_documento: str
    numero_documento: str
    tipo_comprobante: str 
    ruc_factura: Optional[str] = None
    razon_social: Optional[str] = None
    crear_cuenta: bool = False
    contrasena: Optional[str] = None

class EnvioCheckout(BaseModel):
    metodo_despacho: str 
    costo_envio: Decimal = Decimal("0.00")
    departamento: Optional[str] = None
    provincia: Optional[str] = None
    distrito: Optional[str] = None
    direccion: Optional[str] = None
    referencia: Optional[str] = None
    fecha_recojo: Optional[str] = None
    horario_recojo: Optional[str] = None
    receptor_tipo: str = "mismo_cliente"
    receptor_nombres: Optional[str] = None
    receptor_documento_tipo: Optional[str] = None
    receptor_documento_num: Optional[str] = None
    receptor_celular: Optional[str] = None

class ItemCheckout(BaseModel):
    id_producto: str
    cantidad: int = Field(..., gt=0) 
    title: Optional[str] = None
    unit_price: Optional[Decimal] = None

class CrearPedidoRequest(BaseModel):
    cliente: ClienteCheckout
    envio: EnvioCheckout
    items: List[ItemCheckout] = Field(..., min_items=1)
    codigo_cupon: Optional[str] = None
    metodo_pago: str

class MPFormData(BaseModel):
    token: Optional[str] = None
    issuer_id: Optional[str] = None
    payment_method_id: str
    transaction_amount: float
    installments: int = 1
    payer: dict

class PagoTransparenteRequest(BaseModel):
    cliente: ClienteCheckout
    envio: EnvioCheckout
    items: List[ItemCheckout] = Field(..., min_items=1)
    codigo_cupon: Optional[str] = None
    mp_data: MPFormData
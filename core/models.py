from django.db import models

from datetime import datetime
from django.utils import timezone

# Create your models here.
from django.db import models

class Proveedor(models.Model):
    ruc = models.CharField(max_length=11, unique=True)
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} - {self.ruc}"

class Compra(models.Model):
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha = models.DateField()
    tipo_comprobante = models.CharField(max_length=20, choices=[
        ('FA', 'Factura'),
        ('BO', 'Boleta'),
        ('NC', 'Nota de crédito'),
    ])
    serie = models.CharField(max_length=4)
    numero = models.CharField(max_length=8)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.tipo_comprobante}-{self.serie}-{self.numero}"
    

class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('Producto', on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.producto.descripcion} x {self.cantidad}"



class Producto(models.Model):
    cod = models.CharField(max_length=50, null=False)  # por ej. COD-001
    descripcion = models.CharField(max_length=200)              # ej. LUNA BLANCA 1.56
    tipo = models.CharField(max_length=100, choices=[('Monturas oftálimcas', 'Monturas oftálimcas'), ('Monturas de sol', 'Monturas de sol'), ('Lectores', 'Lectores'), ('Lentes de Contacto', 'Lentes de Contacto'), ('Lentes de Contacto', 'Lentes de Contacto'), ('Accesorios', 'Accesorios')])  # Lunas, Monturas, Accesorios
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)                 # stock actual
    talla = models.CharField(max_length=50, blank=True, null=True)       # si aplica
    activo = models.BooleanField(default=True)             # por si luego das de baja productos   
    costo_promedio = models.DecimalField(max_digits=10, decimal_places=4, default=0
)



    def __str__(self):
        return f"{self.cod} - {self.descripcion}"

class Cliente(models.Model):
    OPTOMETRA_CHOICES = [
        ('Hellen', 'Hellen'),
        ('Xiomara', 'Xiomara'),
        ('Javier', 'Javier'),
        ('Lucita', 'Lucita'),
        ('Óptica_IC', 'Óptica IC'),        
        ('Solidaridad', 'Solidaridad'),
        ('La Luz', 'La Luz'),
        ('Ñahui', 'Ñahui'),
        ('Internacional', 'Internacional'),
        ('Opeluce', 'Opeluce'),
        ('Otras_Clinicas', 'Otras Clinicas'),
        ('Blanquita', 'Blanquita'),
        ('Rojita', 'Rojita'),
        ('Paola', 'Paola'),
        ('Denis', 'Denis'),
        ('Otros', 'Otros'),
        ]


    DNI = models.CharField(max_length=20, blank=True, null=True)
    nombre = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    Edad = models.FloatField(max_length=3, null=True, blank=True)    
    fecha_registro = models.DateField(default=timezone.localdate)
    Optometra = models.CharField(max_length=20, choices=OPTOMETRA_CHOICES, null=True, blank=True) 

    def __str__(self):
        return self.nombre

class MedidaVista(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='medidas')
    #fecha_registro = models.DateField(default=timezone.localdate)
    fecha_registro = models.DateField(blank=True, null=True)
    Optometra = models.CharField(max_length=150, blank=True, null=True)


    esf_lejos_OD = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cil_lejos_OD = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_lejos_OD = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_lejos_OD = models.FloatField(max_length=6, default=0)
    Add_lejos_OD = models.DecimalField(max_digits=6, decimal_places=2 ,null=True, blank=True, default=0.00)
    AV_lejos_OD = models.CharField(max_length=6, null=True, blank=True)
    
    esf_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)    
    cil_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_lejos_OI = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_lejos_OI = models.FloatField(max_length=6, default=0)
    Add_lejos_OI = models.DecimalField(max_digits=6,decimal_places=2, default=0.00)
    AV_lejos_OI = models.CharField(max_length=6, null=True, blank=True)

    esf_cerca_OD = models.DecimalField(max_digits=6, decimal_places=2, default=0.00 )
    cil_cerca_OD = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_cerca_OD = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_cerca_OD = models.FloatField(max_length=6, default=0)
    AV_cerca_OD = models.CharField(max_length=6, null=True, blank=True)
    
    esf_cerca_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    cil_cerca_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_cerca_OI = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_cerca_OI = models.FloatField(max_length=6, default=0)
    AV_cerca_OI = models.CharField(max_length=6, null=True, blank=True)

    descripcion = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f'Medidas de {self.cliente.nombre}'


class Venta(models.Model):
    factura = models.CharField(max_length=4, blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, blank=True, null=True)
    descripcion = models.CharField(max_length=255, null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f'Venta {self.id} - {self.fecha}'

class Gasto(models.Model):
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField()

    def __str__(self):
        return self.descripcion


class TipoLunas(models.Model):
    ENFOQUE_CHOICES = [
        ('Monofocal', 'Monofocal'),
        ('Bifocal_Fla', 'Bifocal Flat Top:'),
        ('Bifocal_in', 'Bifocal Invisible:'),
        ('Multifocal', 'Multifocal'),
        ('Lentes_Contac', 'Lentes de Contacto'),
    ]

    TIPO_MULTIFOCAL_CHOICES = [
        ('Convencional', 'Convencional:'),
        ('Digital', 'Digital:'),
    ]

    MARCA_MULTIFOCAL_CHOICES = [
        ('Essilor', 'Essilor'),
        ('Varilux', 'Varilux'),
        ('Adaptar', 'Adaptar'),
        ('Good', 'Good'),
        ('Amplitud', 'Amplitud'),
        ('Digital', 'Digital'),

    ]

    MATERIAL_CHOICES = [
        ('Vidrio', 'Vidrio'),
        ('Resina', 'Resina'),
        ('Policarbonato', 'Policarbonato'),
        ('Futurex', 'Futurex'),   
    ]

    TRATAMIENTO_CHOICES = [
        ('sin_tratamiento', 'Sin tratamiento'),
        ('UV', 'UV'),
        ('AR', 'UV + AR'),
        ('Blue', 'UV + AR + Blue Protect'),
        ('Fotocromatico', 'UV + AR + Fotocromático'),
        ('FotoBlue', 'UV + AR + Blue Protect + Fotomatic'),
        ('Transition', 'UV + AR + Transition'),
    ]

    COLOR_CHOICES = [
        ('Azul', 'Azul'),
        ('Verde', 'Verde'),
        ('Gris', 'Gris'),
        ('Marron', 'Marrón'),
        ('Rosado', 'Rosado'),
        ('Verde', 'Verde grafito'),
        ('zafiro', 'Zafiro'),
        ('ambar', 'ámbar'),
        ('esmeralda', 'Esmeralda'),
        ('rubi', 'Rubí'),
    ]

    FABRICACION_CHOICES = [
        ('Curva', 'Curva'),
        ('Reduccion', 'Reducción'),
        ('AltoIndice', 'Alto Índice')
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='lunas')  # 👈 este es el campo faltante
    enfoque = models.CharField(max_length=20, choices=ENFOQUE_CHOICES,null=True, blank=True)
    tipo_multifocal = models.CharField(max_length=20, choices=TIPO_MULTIFOCAL_CHOICES, null=True, blank=True)
    marca_multifocal = models.CharField(max_length=20, choices=MARCA_MULTIFOCAL_CHOICES, null=True, blank=True)
    material = models.CharField(max_length=20, choices=MATERIAL_CHOICES, null=True, blank=True)
    tratamiento = models.CharField(max_length=20, choices=TRATAMIENTO_CHOICES, null=True, blank=True)
    colorfotosensible = models.CharField(max_length=20, choices=COLOR_CHOICES, null=True, blank=True)
    fabricacion = models.CharField(max_length=20, choices=FABRICACION_CHOICES, null=True, blank=True)

    def __str__(self):
        return f"{self.enfoque} - {self.tipo_multifocal} - {self.material}"


class Temporal(models.Model):
    DNI = models.CharField(max_length=20, blank=True, null=True)
    nombre = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    Edad = models.FloatField(max_length=3, null=True, blank=True)    
    fecha_registro = models.DateTimeField(auto_now_add=True, blank=True)

    lunas = models.CharField(max_length=255, blank=True)
    monturas = models.CharField(max_length=255, blank=True)

    esf_lejos_OD = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    cil_lejos_OD = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    eje_lejos_OD = models.DecimalField(max_digits=6, decimal_places=0, blank=True)
    DIP_lejos_OD = models.FloatField(max_length=6, blank=True)
    Add_lejos_OD = models.DecimalField(max_digits=6, decimal_places=0 ,null=True, blank=True)
    AV_lejos_OD = models.FloatField(max_length=6, null=True, blank=True)
    
    esf_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, blank=True)    
    cil_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    eje_lejos_OI = models.DecimalField(max_digits=6, decimal_places=0, blank=True)
    DIP_lejos_OI = models.FloatField(max_length=6, blank=True)
    Add_lejos_OI = models.DecimalField(max_digits=6,decimal_places=2, null=True, blank=True)
    AV_lejos_OI = models.FloatField(max_length=6, null=True, blank=True)

    esf_cerca_OD = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    cil_cerca_OD = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    eje_cerca_OD = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    DIP_cerca_OD = models.FloatField(max_length=6, blank=True)
    AV_cerca_OD = models.FloatField(max_length=6, null=True, blank=True)
    
    esf_cerca_OI = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    cil_cerca_OI = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    eje_cerca_OI = models.DecimalField(max_digits=6, decimal_places=2, blank=True)
    DIP_cerca_OI = models.FloatField(max_length=6, blank=True)
    AV_cerca_OI = models.FloatField(max_length=6, null=True, blank=True)

    def __str__(self):
        return self.nombre


# Implementacion de facturas
from django.db import models
from .models import Cliente  # Asegúrate de importar Cliente si está en otro archivo

class TicketVenta(models.Model):
    numero = models.PositiveIntegerField()
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True)
    vendedor = models.CharField(max_length=100)
    fecha_emision = models.DateField(auto_now_add=True)
    hora_emision = models.TimeField(auto_now_add=True)
    fecha_entrega = models.CharField(max_length=20, blank=True, null=True)
    hora_entrega = models.CharField(max_length=20, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    a_cuenta = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    puntos_ic = models.PositiveIntegerField(default=0)

    def __str__(self):
        cliente = self.cliente.nombre if self.cliente else 'Sin cliente'
        return f"Recibo N° {self.numero} - {cliente}"


class DetalleTicketVenta(models.Model):
    ticket_numero = models.ForeignKey(TicketVenta, related_name='detalles', on_delete=models.CASCADE)
    
    producto = models.ForeignKey('Producto', on_delete=models.PROTECT, null=True, blank=True)
    
    descripcion = models.TextField()
    cantidad = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        # Muestra el número real del ticket:
        num = getattr(self.ticket_numero, "numero", 0)
        return f"{num:06d} - {self.descripcion[:30]}"

class ReciboCorrelativo(models.Model):
    numero_actual = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Recibo N° {self.numero_actual}"

from decimal import Decimal
from django.utils import timezone

class KardexMovimiento(models.Model):
    TIPO_CHOICES = (
        ('IN', 'Entrada'),
        ('OUT', 'Salida'),
    )

    producto = models.ForeignKey(
        'Producto',
        on_delete=models.CASCADE,
        related_name='kardex'
    )

    fecha = models.DateTimeField(default=timezone.now)

    tipo = models.CharField(
        max_length=3,
        choices=TIPO_CHOICES
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    costo_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )

    costo_total = models.DecimalField(
        max_digits=12,
        decimal_places=4
    )

    stock_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    stock_actual = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    costo_promedio = models.DecimalField(
        max_digits=10,
        decimal_places=4
    )

    # Referencias
    compra = models.ForeignKey(
        'Compra',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    ticket = models.ForeignKey(
        'TicketVenta',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['fecha']

    def __str__(self):
        return f"{self.producto} {self.tipo} {self.cantidad}"


class CajaDia(models.Model):
    fecha = models.DateField(unique=True)
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cerrada = models.BooleanField(default=False)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    observacion = models.CharField(max_length=255, blank=True, default="")


        # ✅ Arqueo por medio de pago
    arqueo_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    arqueo_yape = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    arqueo_tarjeta = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    arqueo_transferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # ✅ Diferencias (arqueo - sistema)
    dif_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dif_yape = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dif_tarjeta = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dif_transferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


    def __str__(self):
        return f"Caja {self.fecha} ({'CERRADA' if self.cerrada else 'ABIERTA'})"

    @property
    def total_ingresos(self):
        return self.movimientos.filter(tipo="IN").aggregate(s=models.Sum("monto"))["s"] or Decimal("0.00")

    @property
    def total_egresos(self):
        return self.movimientos.filter(tipo="OUT").aggregate(s=models.Sum("monto"))["s"] or Decimal("0.00")

    @property
    def saldo_final(self):
        return Decimal(self.saldo_inicial) + Decimal(self.total_ingresos) - Decimal(self.total_egresos)


class MovimientoCaja(models.Model):
    TIPO_CHOICES = (("IN", "Ingreso"), ("OUT", "Egreso"))
    MEDIO_CHOICES = (
        ("EFECTIVO", "Efectivo"),
        ("YAPE", "Yape"),
        ("PLIN", "Plin"),
        ("TARJETA", "Tarjeta"),
        ("TRANSFERENCIA", "Transferencia"),
        ("OTRO", "Otro"),
    )
    CATEGORIA_CHOICES = (
        ("VENTA", "Venta"),
        ("COBRANZA", "Cobranza"),
        ("COMPRA", "Compra"),
        ("GASTO", "Gasto"),
        ("AJUSTE", "Ajuste"),
        ("OTRO", "Otro"),
    )
    FUENTE_CHOICES = (
        ("MANUAL", "Manual"),
        ("TICKET", "Ticket"),
        ("COMPRA", "Compra"),
    )

    caja = models.ForeignKey(CajaDia, related_name="movimientos", on_delete=models.CASCADE)
    fecha_hora = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=3, choices=TIPO_CHOICES)
    medio_pago = models.CharField(max_length=20, choices=MEDIO_CHOICES, default="EFECTIVO")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default="OTRO")
    descripcion = models.CharField(max_length=255, blank=True, default="")
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    # Enlaces opcionales (si ya tienes estos modelos)
    ticket = models.ForeignKey("TicketVenta", null=True, blank=True, on_delete=models.SET_NULL)
    compra = models.ForeignKey("Compra", null=True, blank=True, on_delete=models.SET_NULL)

    fuente = models.CharField(max_length=20, choices=FUENTE_CHOICES, default="MANUAL")

    class Meta:
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.caja.fecha} {self.tipo} {self.monto} ({self.medio_pago})"


class PagoTicket(models.Model):
    MEDIO_CHOICES = (
        ("EFECTIVO", "Efectivo"),
        ("YAPE", "Yape"),
        ("TARJETA", "Tarjeta"),
        ("TRANSFERENCIA", "Transferencia"),
    )

    ticket = models.ForeignKey("TicketVenta", on_delete=models.CASCADE, related_name="pagos")
    fecha_hora = models.DateTimeField(default=timezone.now)
    medio_pago = models.CharField(max_length=20, choices=MEDIO_CHOICES)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Pago {self.ticket.numero} {self.medio_pago} {self.monto}"


# pantalla TV
class OrdenTrabajo(models.Model):
    ESTADOS = (
        ("LAB_PEDIDO", "Pedido al Laboratorio"),
        ("LAB_EN_PROCESO", "En Laboratorio"),
        ("BISELADO", "En Biselado"),
        ("UV", "Desinfección UV"),
        ("LISTO", "Lentes Listos"),
        ("ENTREGADO", "Entregado"),
    )

    ticket = models.OneToOneField("TicketVenta", on_delete=models.CASCADE, related_name="orden")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="LAB_PEDIDO")

    fecha_hora_creacion = models.DateTimeField(default=timezone.now)
    fecha_hora_ultima_actualizacion = models.DateTimeField(auto_now=True)

    # Timestamps por hito (opcionales pero útiles)
    ts_lab_pedido = models.DateTimeField(null=True, blank=True)
    ts_biselado = models.DateTimeField(null=True, blank=True)
    ts_uv = models.DateTimeField(null=True, blank=True)
    ts_listo = models.DateTimeField(null=True, blank=True)
    ts_entregado = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"OT Ticket {self.ticket.numero} - {self.estado}"



    def due_datetime(self):
        """
        Convierte fecha_entrega + hora_entrega del Ticket
        Soporta:
        - YYYY-MM-DD + HH:MM
        - DD/MM/YYYY + HH:MM
        - HH:MM a. m. / p. m.
        """
        t = self.ticket
        if not t or not t.fecha_entrega or not t.hora_entrega:
            return None

        fecha = t.fecha_entrega.strip()
        hora = t.hora_entrega.strip().lower()

        # Normalizar AM/PM
        hora = (
            hora.replace("a. m.", "am")
                .replace("p. m.", "pm")
                .replace("a.m.", "am")
                .replace("p.m.", "pm")
        )

        formatos_fecha = ["%Y-%m-%d", "%d/%m/%Y"]
        formatos_hora = ["%H:%M", "%I:%M %p"]

        for f_fmt in formatos_fecha:
            for h_fmt in formatos_hora:
                try:
                    dt = datetime.strptime(f"{fecha} {hora}", f"{f_fmt} {h_fmt}")
                    return timezone.make_aware(dt)
                except ValueError:
                    continue

        return None


    def minutos_retraso(self):
        due = self.due_datetime()
        if not due:
            return 0

        # ✅ Freeze del retraso:
        # - ENTREGADO: se fija al momento de entrega
        # - LISTO: se fija al momento que quedó listo
        # - En proceso: sigue corriendo contra ahora
        if self.ts_entregado:
            fin = self.ts_entregado
        elif self.estado == "LISTO" and self.ts_listo:
            fin = self.ts_listo
        else:
            fin = timezone.now()

        delta = fin - due
        mins = int(delta.total_seconds() // 60)
        return mins if mins > 0 else 0


    def a_tiempo(self):
        return self.minutos_retraso() == 0

    def estado_publico(self):
        """
        Texto corto para TV.
        """
        m = dict(self.ESTADOS)
        return m.get(self.estado, self.estado)



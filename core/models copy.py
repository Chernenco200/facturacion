from django.db import models

# Create your models here.
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
    cod = models.CharField(max_length=50)  # por ej. COD-001
    descripcion = models.CharField(max_length=200)              # ej. LUNA BLANCA 1.56
    tipo = models.CharField(max_length=100, choices=[('Monturas oftálimcas', 'Monturas oftálimcas'), ('Monturas de sol', 'Monturas de sol'), ('Lectores', 'Lectores'), ('Lentes de Contacto', 'Lentes de Contacto'), ('Lentes de Contacto', 'Lentes de Contacto'), ('Accesorios', 'Accesorios')])  # Lunas, Monturas, Accesorios
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)                 # stock actual
    talla = models.CharField(max_length=50, blank=True, null=True)       # si aplica
    activo = models.BooleanField(default=True)             # por si luego das de baja productos

    def __str__(self):
        return f"{self.cod} - {self.descripcion}"







class Cliente(models.Model):
    
    DNI = models.CharField(max_length=20, blank=True, null=True)
    nombre = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    Edad = models.FloatField(max_length=3, null=True, blank=True)    
    fecha_registro = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class MedidaVista(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='medidas')
    
    esf_lejos_OD = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cil_lejos_OD = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_lejos_OD = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_lejos_OD = models.FloatField(max_length=6)
    Add_lejos_OD = models.DecimalField(max_digits=6, decimal_places=2 ,null=True, blank=True, default=0.00)
    AV_lejos_OD = models.CharField(max_length=6, null=True, blank=True)
    
    esf_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)    
    cil_lejos_OI = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    eje_lejos_OI = models.DecimalField(max_digits=6, decimal_places=0, default=0)
    DIP_lejos_OI = models.FloatField(max_length=6, default=0.00)
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
        ('Gris', 'Gris'),
        ('Marron', 'Marrón'),
        ('Rosado', 'Rosado'),
        ('Verde', 'Verde grafito'),
        ('zafiro', 'Zafiro'),
        ('ambar', 'ámbar'),
        ('esmeralda', 'Esmeralda'),
        ('amatista', 'amatista'),
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
    fecha_registro = models.DateField(auto_now_add=True, blank=True)

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

from django.db import models
from django import forms
from .models import Cliente, MedidaVista, Venta, Producto, TipoLunas, Proveedor, Compra, DetalleCompra, DetalleTicketVenta


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['cod','descripcion', 'precio_venta', 'precio_compra', 'stock', 'tipo', 'talla', 'activo', 'imagenF', 'imagenL', 'imagenD']

        widgets = {
            'cod': forms.TextInput(attrs={'id': 'id_cod'}),
            'descripcion': forms.TextInput(attrs={'id': 'id_descripcion'}),
            'precio_venta': forms.NumberInput(attrs={'id': 'id_precio_venta'}),
            'precio_compra': forms.NumberInput(attrs={'id': 'id_precio_compra'}),
            'stock': forms.NumberInput(attrs={'id': 'id_stock'}),
            'tipo': forms.TextInput(attrs={'id': 'id_tipo'}),
            'talla': forms.NumberInput(attrs={'id': 'id_talla'}),
            'activo': forms.TextInput(attrs={'id': 'id_activo'}),
        }        

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['DNI', 'nombre', 'telefono', 'Edad', 'fecha_registro', 'Optometra']

        widgets = {
            "DNI": forms.TextInput(attrs={"class": "form-control"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "Edad": forms.NumberInput(attrs={"class": "form-control"}),
            "fecha_registro": forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
                format="%Y-%m-%d"
            ),
            "Optometra": forms.Select(attrs={"class": "form-control"}),
        }


class MedidaVistaForm(forms.ModelForm):
    class Meta:
        model = MedidaVista
        exclude = ['cliente']
        fields = ['esf_lejos_OD', 'cil_lejos_OD', 'eje_lejos_OD', 'DIP_lejos_OD','Add_lejos_OD', 'AV_lejos_OD',
                  'esf_lejos_OI', 'cil_lejos_OI', 'eje_lejos_OI', 'DIP_lejos_OI','Add_lejos_OI', 'AV_lejos_OI',
                  'esf_cerca_OD', 'cil_cerca_OD', 'eje_cerca_OD', 'DIP_cerca_OD', 'AV_cerca_OD',
                  'esf_cerca_OI', 'cil_cerca_OI', 'eje_cerca_OI', 'DIP_cerca_OI', 'AV_cerca_OI',
                  'descripcion']
        widgets = {
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Anota aquí recomendaciones, tipo de uso, ocupación, indicaciones para el laboratorio…'
            })
        }

    # -----------------------------------Aplicar step -----------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Campos con step 0.25
        step_025 = [
            'esf_lejos_OD', 'cil_lejos_OD', 'Add_lejos_OD', 'AV_lejos_OD',
            'esf_lejos_OI', 'cil_lejos_OI', 'Add_lejos_OI', 'AV_lejos_OI',
            'esf_cerca_OD', 'cil_cerca_OD', 'AV_cerca_OD',
            'esf_cerca_OI', 'cil_cerca_OI', 'AV_cerca_OI'
        ]
        
        # Campos con step 1
        step_1 = [
            'eje_lejos_OD', 'DIP_lejos_OD', 'eje_lejos_OI', 'DIP_lejos_OI',
            'eje_cerca_OD', 'DIP_cerca_OD', 'eje_cerca_OI', 'DIP_cerca_OI'
        ]

        for field in step_025:
            if field in self.fields:
                self.fields[field].widget.attrs.update({'step': '0.25'})
        
        for field in step_1:
            if field in self.fields:
                self.fields[field].widget.attrs.update({'step': '1'})

    #------------------------------------------------------------------------

class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['cliente', 'total']

class TipoLunasForm(forms.ModelForm):
    class Meta:
        model = TipoLunas
        exclude = ['cliente']
        fields = ['enfoque', 'tipo_multifocal','marca_multifocal', 'material', 'tratamiento', 'colorfotosensible', 'fabricacion']
        widgets = {
            'enfoque': forms.Select(attrs={'class': 'form-control'}),
            'tipo_multifocal': forms.Select(attrs={'class': 'form-control'}),
            'marca_multifocal': forms.Select(attrs={'class': 'form-control'}),
            'material': forms.Select(attrs={'class': 'form-control'}),
            'tratamiento': forms.Select(attrs={'class': 'form-control'}),
            'colorfotosensible': forms.Select(attrs={'class': 'form-control'}),
            'fabricacion': forms.Select(attrs={'class': 'form-control'}),
        }

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ['ruc', 'nombre', 'direccion', 'telefono', 'email', 'activo']


class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ['proveedor', 'fecha', 'tipo_comprobante', 'serie', 'numero']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Proveedores activos, más el de la compra si se está editando.
        self.fields['proveedor'].queryset = (
            Proveedor.objects
            .filter(
                models.Q(activo=True)
                | models.Q(pk=getattr(self.instance, 'proveedor_id', None))
            )
            .order_by('nombre')
        )

        for nombre, campo in self.fields.items():
            clase = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'
            campo.widget.attrs.setdefault('class', clase)

        self.fields['serie'].widget.attrs.setdefault('placeholder', 'F001')
        self.fields['numero'].widget.attrs.setdefault('placeholder', '00012345')

    def clean_serie(self):
        return (self.cleaned_data.get('serie') or '').strip().upper()

    def clean_numero(self):
        return (self.cleaned_data.get('numero') or '').strip()


class DetalleCompraForm(forms.ModelForm):
    class Meta:
        model = DetalleCompra
        fields = ['producto', 'cantidad', 'precio_compra', 'precio_venta']


class DetalleTicketVentaForm(forms.ModelForm):
    """Corrige descripción, cantidad o precio de un producto vendido."""

    class Meta:
        model = DetalleTicketVenta
        fields = ['descripcion', 'cantidad', 'precio']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
        }

    def clean_cantidad(self):
        cantidad = self.cleaned_data.get('cantidad')
        if not cantidad or cantidad < 1:
            raise forms.ValidationError('La cantidad debe ser al menos 1.')
        return cantidad

    def clean_precio(self):
        precio = self.cleaned_data.get('precio')
        if precio is None or precio < 0:
            raise forms.ValidationError('El precio no puede ser negativo.')
        return precio


class DescripcionVentaForm(forms.ModelForm):
    """Para ventas contabilizadas: solo se corrige el texto."""

    class Meta:
        model = DetalleTicketVenta
        fields = ['descripcion']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

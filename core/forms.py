from django import forms
from .models import Cliente, MedidaVista, Venta, Producto, TipoLunas, Proveedor, Compra, DetalleCompra


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
        fields = ['DNI', 'nombre', 'telefono', 'Edad', 'fecha_registro','Optometra']

        widgets = {
            "fecha_registro": forms.DateInput(
                attrs={"type": "date", "class": "form-control form-control-sm"}
            )
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
        fields = ['proveedor', 'fecha', 'tipo_comprobante', 'serie', 'numero', 'total']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'})
        }


class DetalleCompraForm(forms.ModelForm):
    class Meta:
        model = DetalleCompra
        fields = ['producto', 'cantidad', 'precio_compra', 'precio_venta']


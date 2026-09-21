from django import forms

from .models import (
    ConceptoOperacion,
    CuentaContable,
    CategoriaGerencial,
    CentroCosto,
)


class ConceptoOperacionForm(forms.ModelForm):
    class Meta:
        model = ConceptoOperacion

        fields = [
            "codigo",
            "nombre",
            "concepto_padre",
            "es_grupo",
            "tipo_operacion",
            "cuenta_contable",
            "categoria_gerencial",
            "centro_costo",
            "palabras_clave",
            "sinonimos",
            "requiere_proveedor",
            "requiere_cliente",
            "requiere_comprobante",
            "requiere_centro_costo",
            "permite_cambiar_cuenta",
            "es_fijo",
            "es_variable",
            "descripcion",
            "activo",
            "orden",
        ]

        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. GAS-ALQ-001",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Alquiler del local",
                }
            ),
            "concepto_padre": forms.Select(
                attrs={"class": "form-control"}
            ),
            "es_grupo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "tipo_operacion": forms.Select(
                attrs={"class": "form-control"}
            ),
            "cuenta_contable": forms.Select(
                attrs={"class": "form-control"}
            ),
            "categoria_gerencial": forms.Select(
                attrs={"class": "form-control"}
            ),
            "centro_costo": forms.Select(
                attrs={"class": "form-control"}
            ),
            "palabras_clave": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "alquiler, renta, arrendamiento",
                }
            ),
            "sinonimos": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "alquiler local, renta local",
                }
            ),
            "requiere_proveedor": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "requiere_cliente": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "requiere_comprobante": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "requiere_centro_costo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "permite_cambiar_cuenta": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "es_fijo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "es_variable": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Descripción o criterio de uso del concepto.",
                }
            ),
            "activo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "orden": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                }
            ),
        }

        labels = {
            "codigo": "Código",
            "nombre": "Nombre del concepto",
            "concepto_padre": "Concepto / grupo padre",
            "es_grupo": "Es un grupo",
            "tipo_operacion": "Tipo de operación",
            "cuenta_contable": "Cuenta contable",
            "categoria_gerencial": "Categoría gerencial",
            "centro_costo": "Centro de costo",
            "palabras_clave": "Palabras clave",
            "sinonimos": "Sinónimos",
            "requiere_proveedor": "Requiere proveedor",
            "requiere_cliente": "Requiere cliente",
            "requiere_comprobante": "Requiere comprobante",
            "requiere_centro_costo": "Requiere centro de costo",
            "permite_cambiar_cuenta": "Permitir cambiar cuenta contable",
            "es_fijo": "Costo / gasto fijo",
            "es_variable": "Costo / gasto variable",
            "descripcion": "Descripción",
            "activo": "Activo",
            "orden": "Orden",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Solo cuentas utilizables.
        self.fields["cuenta_contable"].queryset = (
            CuentaContable.objects
            .filter(
                activo=True,
                acepta_movimientos=True,
            )
            .order_by("codigo")
        )

        self.fields["categoria_gerencial"].queryset = (
            CategoriaGerencial.objects
            .filter(activo=True)
            .order_by("codigo")
        )

        self.fields["centro_costo"].queryset = (
            CentroCosto.objects
            .filter(activo=True)
            .order_by("codigo")
        )

        # Los grupos pueden ser padres de otros conceptos.
        conceptos_padre = (
            ConceptoOperacion.objects
            .filter(
                activo=True,
                es_grupo=True,
            )
            .order_by("orden", "nombre")
        )

        # Al editar, impedir que el concepto sea padre de sí mismo.
        if self.instance and self.instance.pk:
            conceptos_padre = conceptos_padre.exclude(
                pk=self.instance.pk
            )

        self.fields["concepto_padre"].queryset = conceptos_padre

        # Campos opcionales.
        self.fields["concepto_padre"].required = False
        self.fields["cuenta_contable"].required = False
        self.fields["categoria_gerencial"].required = False
        self.fields["centro_costo"].required = False

        self.fields["concepto_padre"].empty_label = "— Sin grupo padre —"
        self.fields["cuenta_contable"].empty_label = "— Sin cuenta contable —"
        self.fields["categoria_gerencial"].empty_label = "— Sin categoría —"
        self.fields["centro_costo"].empty_label = "— Sin centro de costo —"

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip()

        if not codigo:
            raise forms.ValidationError(
                "Debe ingresar un código."
            )

        qs = ConceptoOperacion.objects.filter(
            codigo__iexact=codigo
        )

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError(
                "Ya existe un concepto con este código."
            )

        return codigo

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()

        if not nombre:
            raise forms.ValidationError(
                "Debe ingresar el nombre del concepto."
            )

        return nombre

    def clean(self):
        cleaned_data = super().clean()

        es_grupo = cleaned_data.get("es_grupo")
        cuenta_contable = cleaned_data.get("cuenta_contable")
        es_fijo = cleaned_data.get("es_fijo")
        es_variable = cleaned_data.get("es_variable")
        requiere_centro_costo = cleaned_data.get(
            "requiere_centro_costo"
        )
        centro_costo = cleaned_data.get("centro_costo")

        # Un grupo sirve para organizar conceptos;
        # no debería generar contabilización directamente.
        if es_grupo and cuenta_contable:
            self.add_error(
                "cuenta_contable",
                "Un concepto marcado como grupo no debe tener "
                "una cuenta contable de movimiento."
            )

        if es_fijo and es_variable:
            self.add_error(
                "es_variable",
                "El concepto no puede ser fijo y variable "
                "al mismo tiempo."
            )

        if requiere_centro_costo and not centro_costo:
            self.add_error(
                "centro_costo",
                "Debe seleccionar un centro de costo porque "
                "el concepto lo requiere."
            )

        return cleaned_data
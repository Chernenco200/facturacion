from django.contrib import admin
from django.utils.html import format_html
from .models import Producto

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("cod", "descripcion", "tipo", "precio_venta", "stock", "activo", "thumb_f", "thumb_d", "thumb_l")
    search_fields = ("cod", "descripcion")
    list_filter = ("tipo", "activo")
    readonly_fields = ("preview_f", "preview_d", "preview_l")

    fieldsets = (
        ("Datos del producto", {
            "fields": ("cod", "activo", "descripcion", "tipo", "precio_venta", "stock", "talla", "puente", "largo", "ancho", "altura")
        }),
        ("Fotos", {
            "fields": ("imagenF", "preview_f", "imagenD", "preview_d", "imagenL", "preview_l")
        }),
    )

    # miniaturas en listado
    def thumb_f(self, obj):
        return self._thumb(obj.imagenF)
    thumb_f.short_description = "Foto F"

    def thumb_d(self, obj):
        return self._thumb(obj.imagenD)
    thumb_d.short_description = "Foto D"

    def thumb_l(self, obj):
        return self._thumb(obj.imagenL)
    thumb_l.short_description = "Foto L"

    def _thumb(self, img):
        if img:
            return format_html('<img src="{}" style="height:40px;border-radius:6px;" />', img.url)
        return "—"

    # previews grandes en el formulario
    def preview_f(self, obj):
        return self._preview(obj.imagenF)
    preview_f.short_description = "Vista previa F"

    def preview_d(self, obj):
        return self._preview(obj.imagenD)
    preview_d.short_description = "Vista previa D"

    def preview_l(self, obj):
        return self._preview(obj.imagenL)
    preview_l.short_description = "Vista previa L"

    def _preview(self, img):
        if img:
            return format_html('<img src="{}" style="max-height:220px;border-radius:10px;" />', img.url)
        return "Sin imagen"

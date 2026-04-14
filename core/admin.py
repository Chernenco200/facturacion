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
            "fields": ("cod", "activo", "marca", "descripcion", "tipo", "precio_venta", "stock", "talla", "puente", "largo", "ancho", "altura", "condicion", "uso" )
        }),
        ("Fotos", {
            "fields": ("imagenF", "preview_f", "imagenD", "preview_d", "imagenL", "preview_l")
        }),
    )

    def thumb_f(self, obj): return self._thumb(obj.imagenF)
    thumb_f.short_description = "Foto F"

    def thumb_d(self, obj): return self._thumb(obj.imagenD)
    thumb_d.short_description = "Foto D"

    def thumb_l(self, obj): return self._thumb(obj.imagenL)
    thumb_l.short_description = "Foto L"

    def preview_f(self, obj): return self._preview(obj.imagenF)
    preview_f.short_description = "Vista previa F"

    def preview_d(self, obj): return self._preview(obj.imagenD)
    preview_d.short_description = "Vista previa D"

    def preview_l(self, obj): return self._preview(obj.imagenL)
    preview_l.short_description = "Vista previa L"

    def _thumb(self, img):
        url = self._safe_url(img)
        if not url:
            return "—"
        return format_html('<img src="{}" style="height:40px;border-radius:6px;" />', url)

    def _preview(self, img):
        url = self._safe_url(img)
        if not url:
            return "Sin imagen"
        return format_html('<img src="{}" style="max-height:220px;border-radius:10px;" />', url)

    def _safe_url(self, img):
        """
        Devuelve URL solo si es válida.
        En Heroku, cualquier /media/... va a romper, así que lo ocultamos
        hasta que se re-suban a Cloudinary.
        """
        if not img:
            return None
        try:
            url = img.url
        except Exception:
            return None

        # Si quedó como media local, no lo muestres en prod
        if url.startswith("/media/"):
            return None

        return url
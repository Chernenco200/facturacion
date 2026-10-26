from dateutil.relativedelta import relativedelta as R
from django.db.models import Max, Q
from django.utils import timezone
from core.models import Cliente, OrdenTrabajo
from core.seguimiento import ordenes_renovacion, clientes_reactivacion_qs
hoy = timezone.localdate(); a = hoy - R(months=18); b = hoy - R(months=12)
v = (Cliente.objects.exclude(telefono__isnull=True).exclude(telefono="")
     .filter(Q(Edad__gte=18) | Q(Edad__isnull=True))
     .annotate(u=Max("ticketventa__fecha_emision")).filter(u__gt=a, u__lte=b))
con_ot = v.filter(ticketventa__orden__estado="ENTREGADO").distinct()
print("Adultos con telefono y ultima compra de 12 a 18 meses:", v.count())
print("  ...de ellos con alguna orden ENTREGADA:", con_ot.count())
print("Primera orden de trabajo registrada:", OrdenTrabajo.objects.order_by("ticket__fecha_emision").values_list("ticket__fecha_emision", flat=True).first())
print("Lista de renovacion actual:", ordenes_renovacion(hoy).count())
print("Lista de reactivacion actual:", clientes_reactivacion_qs(hoy).count())

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import TicketVenta


class Command(BaseCommand):
    help = "Corrige los saldos de los tickets históricos."

    def handle(self, *args, **options):

        qs = TicketVenta.objects.filter(
            numero__gte=9000000
        )

        total = qs.count()

        self.stdout.write(
            f"Tickets históricos encontrados: {total}"
        )

        with transaction.atomic():

            actualizados = qs.update(
                a_cuenta=total,
                saldo=0
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Tickets actualizados: {actualizados}"
            )
        )
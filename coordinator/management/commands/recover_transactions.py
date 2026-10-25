"""python manage.py recover_transactions  ->  what the coordinator runs after restarting."""
from django.core.management.base import BaseCommand

from coordinator.services import recover


class Command(BaseCommand):
    help = "Finish every transaction left open by a crash (2PC recovery)."

    def handle(self, *args, **options):
        results = recover()
        if not results:
            self.stdout.write("Nothing to recover.")
        for txn_id, action in results:
            self.stdout.write(f"{txn_id}: {action}")

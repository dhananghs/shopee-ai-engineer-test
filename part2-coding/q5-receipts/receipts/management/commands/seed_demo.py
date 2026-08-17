# Puts a few made up receipts in the database so the question page can be
# tried out without having to photograph real receipts first.
#
#   python manage.py seed_demo
#
# The dates are worked out from today, so "what did I buy yesterday" and
# "last 7 days" always have something to find.

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from receipts.insight import save_receipt
from receipts.models import Receipt


def days_ago(number):
    return (date.today() - timedelta(days=number)).isoformat()


DEMO_RECEIPTS = [
    {
        "merchant": "McDonalds Senayan",
        "bought_at": days_ago(1),
        # ordered through a delivery app, so there is a delivery fee and a promo
        "subtotal": 91000, "tax": 10010, "service_charge": 0,
        "delivery_fee": 15000, "discount": 10000,
        "total": 106010,
        "items": [
            {"name": "Big Mac", "category": "food", "quantity": 1, "price": 48000},
            {"name": "French Fries Large", "category": "food", "quantity": 1, "price": 25000},
            {"name": "Coca Cola Medium", "category": "beverage", "quantity": 1, "price": 18000},
        ],
    },
    {
        "merchant": "Burger King Plaza Indonesia",
        "bought_at": days_ago(3),
        "subtotal": 82000, "tax": 9020, "service_charge": 0,
        "delivery_fee": 0, "discount": 0,
        "total": 91020,
        "items": [
            {"name": "Whopper", "category": "food", "quantity": 1, "price": 55000},
            {"name": "Onion Rings", "category": "food", "quantity": 1, "price": 27000},
        ],
    },
    {
        "merchant": "KFC Kemang",
        "bought_at": days_ago(6),
        "subtotal": 99000, "tax": 10890, "service_charge": 0,
        "delivery_fee": 0, "discount": 0,
        "total": 109890,
        "items": [
            {"name": "Fried Chicken 2pcs", "category": "food", "quantity": 2, "price": 38000},
            {"name": "Potato Wedges", "category": "food", "quantity": 1, "price": 23000},
        ],
    },
    {
        # a fixed date so the "total expenses on 20 June" question has an answer
        "merchant": "Warung Tegal Jaya",
        "bought_at": "2026-06-20",
        # eaten in, so there is tax but no delivery
        "subtotal": 102000, "tax": 11220, "service_charge": 0,
        "delivery_fee": 0, "discount": 0,
        "total": 113220,
        "items": [
            {"name": "Nasi Goreng Spesial", "category": "food", "quantity": 2, "price": 25000},
            {"name": "Ayam Geprek", "category": "food", "quantity": 1, "price": 28000},
            {"name": "Es Teh Manis", "category": "beverage", "quantity": 3, "price": 8000},
        ],
    },
]


class Command(BaseCommand):
    help = "Adds a few example receipts so the question page can be tried out"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="remove the example receipts before adding them again",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            # ONLY the made up ones. This used to delete everything, which
            # threw away real receipts somebody had uploaded. Matching on the
            # demo shop names means a real upload is never touched.
            demo_names = [r["merchant"] for r in DEMO_RECEIPTS]
            old = Receipt.objects.filter(merchant__in=demo_names)
            self.stdout.write("removed %d example receipts" % old.count())

            kept = Receipt.objects.exclude(merchant__in=demo_names).count()
            if kept:
                self.stdout.write("left %d real receipt(s) alone" % kept)

            old.delete()

        for reading in DEMO_RECEIPTS:
            receipt = save_receipt(reading)
            self.stdout.write("added %s (%s) - %d items, total %s" % (
                receipt.merchant, receipt.bought_at, receipt.item_count, receipt.total,
            ))

        self.stdout.write(self.style.SUCCESS(
            "done, %d receipts in the database" % Receipt.objects.count()
        ))

# The category list used to be food types - burger, chicken, rice, pizza and
# so on, plus "drink". It got replaced with just food / beverage / other,
# because real Indonesian dishes did not fit any of the old names and all
# ended up as "other".
#
# Rows already in the database still hold the old words, and a search for
# "beverage" would not find a row saying "drink". This changes them over.
#
# The mapping is safe: in the old list everything except "drink" was a kind of
# food, and "other" meant "food I could not put a name to", so all of them
# become "food".

from django.db import migrations

OLD_TO_NEW = {
    "drink": "beverage",
    "burger": "food",
    "chicken": "food",
    "rice": "food",
    "noodle": "food",
    "pizza": "food",
    "side": "food",
    "dessert": "food",
    "salad": "food",
    "other": "food",
}


def to_new_categories(apps, schema_editor):
    ReceiptItem = apps.get_model("receipts", "ReceiptItem")
    for old, new in OLD_TO_NEW.items():
        ReceiptItem.objects.filter(category=old).update(category=new)

    Receipt = apps.get_model("receipts", "Receipt")
    for old, new in OLD_TO_NEW.items():
        Receipt.objects.filter(top_category=old).update(top_category=new)


def back_to_old_categories(apps, schema_editor):
    # The old detail cannot be brought back - once "burger" and "pizza" have
    # both become "food" there is no way to tell them apart again. This just
    # lets the migration be undone without an error.
    ReceiptItem = apps.get_model("receipts", "ReceiptItem")
    ReceiptItem.objects.filter(category="beverage").update(category="drink")

    Receipt = apps.get_model("receipts", "Receipt")
    Receipt.objects.filter(top_category="beverage").update(top_category="drink")


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0003_receipt_delivery_fee_receipt_discount_and_more"),
    ]

    operations = [
        migrations.RunPython(to_new_categories, back_to_old_categories),
    ]

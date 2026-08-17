# Takes what the AI read off the receipt and puts it in the database.
#
# The insight numbers are worked out here in plain python, on purpose. Adding
# up prices is something code does correctly every single time, so there is no
# reason to ask a language model to do it.

from datetime import datetime

from .models import Receipt, ReceiptItem


def parse_date(text):
    """The AI is asked for YYYY-MM-DD. If it sends something else we would
    rather store nothing than store a wrong date."""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def save_receipt(data):
    """data is the dict that extract.read_receipt() returned."""

    items = data.get("items") or []

    receipt = Receipt.objects.create(
        merchant=data.get("merchant", ""),
        bought_at=parse_date(data.get("bought_at")),
        total=data.get("total") or 0,
        subtotal=data.get("subtotal") or 0,
        tax=data.get("tax") or 0,
        service_charge=data.get("service_charge") or 0,
        delivery_fee=data.get("delivery_fee") or 0,
        discount=data.get("discount") or 0,
        raw_json=data,
    )

    saved = []
    for item in items:
        saved.append(ReceiptItem.objects.create(
            receipt=receipt,
            name=item.get("name", ""),
            category=item.get("category", "other"),
            quantity=item.get("quantity") or 1,
            price=item.get("price") or 0,
        ))

    add_insight(receipt, saved)
    return receipt


def add_insight(receipt, items):
    """Works out the summary numbers and saves them on the receipt."""

    receipt.item_count = len(items)

    if items:
        # most expensive is by the price of one item, not the line total,
        # otherwise buying 10 cheap drinks would win
        dearest = max(items, key=lambda i: i.price)
        receipt.most_expensive_item = dearest.name

        # which kind of food most of the money went on
        spent_per_category = {}
        for item in items:
            spent_per_category.setdefault(item.category, 0)
            spent_per_category[item.category] += item.line_total()
        receipt.top_category = max(spent_per_category, key=spent_per_category.get)

    # some receipts do not show a readable grand total, so fall back to
    # adding it up ourselves. the charges have to be in there too, otherwise
    # the total comes out lower than what was really paid.
    if not receipt.total:
        food = sum(item.line_total() for item in items)
        receipt.total = food + receipt.charges()

    receipt.save()
    return receipt

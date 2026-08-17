# The two things the AI is allowed to do.
#
# The AI never touches the database itself and never writes SQL. It only picks
# which of these two functions to call and what to put in the arguments. The
# actual looking up and adding up happens here, in normal Django code.

from datetime import datetime

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum

from receipts.extract import CATEGORIES
from receipts.models import Receipt, ReceiptItem

# price of one item x how many were bought. written this way so the database
# does the multiplying and adding, instead of us pulling every row into python.
LINE_TOTAL = ExpressionWrapper(
    F("price") * F("quantity"),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)


def parse_date(text):
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def clean_category(value):
    """The AI tends to send "drinks" when the database says "drink". Without
    this the filter matches nothing and the user is told they spent zero,
    which is worse than an error because it looks like a real answer."""
    if not value:
        return None

    tidied = value.strip().lower()
    if tidied not in CATEGORIES and tidied.endswith("s"):
        tidied = tidied[:-1]

    # if it is still not one of ours, leave it alone. it will simply find
    # nothing, which is honest. dropping the filter instead would report
    # every kind of food as if it were the one that was asked about.
    return tidied


def base_rows(item_terms=None, merchant=None, date_from=None, date_to=None, category=None):
    """The filtering all the tools share."""

    rows = ReceiptItem.objects.select_related("receipt")

    start = parse_date(date_from)
    end = parse_date(date_to)
    if start:
        rows = rows.filter(receipt__bought_at__gte=start)
    if end:
        rows = rows.filter(receipt__bought_at__lte=end)
    if merchant:
        rows = rows.filter(receipt__merchant__icontains=merchant)
    if category:
        rows = rows.filter(category=clean_category(category))

    # item_terms is a list because the AI is asked to send several words for
    # the same thing - for "hamburger" it sends something like
    # ["hamburger", "burger", "cheeseburger", "whopper"]. We match on any of
    # them, which is how "where did I buy hamburger" finds a Whopper.
    if item_terms:
        matches = Q()
        for term in item_terms:
            matches = matches | Q(name__icontains=term)
        rows = rows.filter(matches)

    return rows


def base_receipts(merchant=None, date_from=None, date_to=None):
    """Same filtering as base_rows, but on whole receipts. Needed because tax
    and delivery fees belong to the receipt, not to any one item."""

    receipts = Receipt.objects.all()

    start = parse_date(date_from)
    end = parse_date(date_to)
    if start:
        receipts = receipts.filter(bought_at__gte=start)
    if end:
        receipts = receipts.filter(bought_at__lte=end)
    if merchant:
        receipts = receipts.filter(merchant__icontains=merchant)

    return receipts


def find_purchases(item_terms=None, merchant=None, date_from=None, date_to=None, limit=20):
    """Lists the things that were bought. Answers questions like
    "what did I buy yesterday" and "where did I buy hamburger"."""

    rows = base_rows(item_terms, merchant, date_from, date_to)
    rows = rows.order_by("-receipt__bought_at")[:limit]

    out = []
    for row in rows:
        out.append({
            "item": row.name,
            "category": row.category,
            "quantity": row.quantity,
            "price": float(row.price),
            "line_total": float(row.line_total()),
            "merchant": row.receipt.merchant,
            "bought_at": str(row.receipt.bought_at),
        })
    return out


def sum_expenses(date_from=None, date_to=None, category=None, merchant=None, group_by=None):
    """Adds money up. Answers "how much did I spend on X".

    group_by can be empty (one grand total), or "day", "merchant" or
    "category" to get the total broken down."""

    rows = base_rows(None, merchant, date_from, date_to, category)

    # Grouping by day or by shop lines up with whole receipts, so the real
    # amount paid can be given for each group. Grouping by category cannot,
    # because one receipt's tax covers several categories at once.
    if group_by in ("day", "merchant") and not category:
        receipt_field = "bought_at" if group_by == "day" else "merchant"
        item_field = "receipt__" + receipt_field

        # two separate queries on purpose. asking for Sum("total") while
        # joined to the items would count the receipt total once per item
        # and give numbers that are far too big.
        paid_per_group = {}
        for group in base_receipts(merchant, date_from, date_to).values(
                receipt_field).annotate(paid=Sum("total")):
            paid_per_group[str(group[receipt_field])] = float(group["paid"] or 0)

        food_per_group = {}
        for group in rows.values(item_field).annotate(food=Sum(LINE_TOTAL)):
            food_per_group[str(group[item_field])] = float(group["food"] or 0)

        out = []
        for name, paid in paid_per_group.items():
            out.append({
                "group": name,
                "total_paid": paid,
                "food_total": food_per_group.get(name, 0.0),
            })
        out.sort(key=lambda row: row["total_paid"], reverse=True)
        return out

    if group_by == "category" or (group_by and category):
        grouped = rows.values("category").annotate(
            food=Sum(LINE_TOTAL)).order_by("-food")
        return [
            {"group": str(g["category"]), "food_total": float(g["food"] or 0)}
            for g in grouped
        ]

    food = rows.aggregate(total=Sum(LINE_TOTAL))["total"] or 0
    answer = {
        "food_total": float(food),
        "number_of_items": rows.count(),
    }

    # Tax, service and delivery belong to the whole receipt, so they cannot be
    # split up per kind of food. When the question is about one category we can
    # only honestly report the food figure. Otherwise we also give back what
    # was really paid, which is the bigger and usually more useful number.
    if not category:
        receipts = base_receipts(merchant, date_from, date_to)
        sums = receipts.aggregate(
            paid=Sum("total"),
            tax=Sum("tax"),
            service=Sum("service_charge"),
            delivery=Sum("delivery_fee"),
            discount=Sum("discount"),
        )
        extra = ((sums["tax"] or 0) + (sums["service"] or 0)
                 + (sums["delivery"] or 0) - (sums["discount"] or 0))

        answer["total_paid"] = float(sums["paid"] or 0)
        answer["extra_charges"] = float(extra)
        answer["number_of_receipts"] = receipts.count()

        # the four charges on their own as well as the combined figure, so an
        # answer about "tax and delivery" can name the right numbers instead
        # of quoting the netted total and calling it tax
        answer["tax"] = float(sums["tax"] or 0)
        answer["service_charge"] = float(sums["service"] or 0)
        answer["delivery_fee"] = float(sums["delivery"] or 0)
        answer["discount"] = float(sums["discount"] or 0)

    return answer


# --- what the AI sees -------------------------------------------------
# The descriptions matter a lot. They are the only thing the AI reads when it
# decides which one to call, so they say WHEN to use each tool, not just what
# it does.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "find_purchases",
            "description": (
                "List food items the user bought. Call this when the user asks "
                "WHAT they bought, WHERE they bought something, or wants to see "
                "individual purchases. Do not use it for totals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Words to look for in the item name. Send several "
                            "related words, because receipts use brand names. "
                            "For 'hamburger' send "
                            "['hamburger','burger','cheeseburger','whopper','big mac']."
                        ),
                    },
                    "merchant": {"type": "string", "description": "Shop name to filter by."},
                    "date_from": {"type": "string", "description": "Earliest date, YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Latest date, YYYY-MM-DD."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sum_expenses",
            "description": (
                "Add up how much money was spent. Call this whenever the user "
                "asks HOW MUCH, for a total, or for spending over a period. "
                "Never add prices up yourself - always call this. It gives back "
                "'food_total' (the food only) and 'total_paid' (what actually "
                "left the wallet, including tax and delivery). 'total_paid' is "
                "missing when a category was asked for, because tax cannot be "
                "split between kinds of food."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Earliest date, YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Latest date, YYYY-MM-DD."},
                    "category": {
                        "type": "string",
                        # listing the allowed values here stops the AI from
                        # inventing its own, which is what made it send
                        # "drinks" when the database says "drink"
                        "enum": CATEGORIES,
                        "description": (
                            "Optional. Only set this when the user names one kind "
                            "of food, like 'drinks' or 'pizza'. Leave it out for "
                            "general questions about food or spending - the word "
                            "'food' on its own means everything, not a category."
                        ),
                    },
                    "merchant": {"type": "string", "description": "Shop name to filter by."},
                    "group_by": {
                        "type": "string",
                        "enum": ["day", "merchant", "category"],
                        "description": (
                            "Leave out for one grand total. Use 'day' for "
                            "questions like 'which day did I spend the most', "
                            "'merchant' for 'where do I spend the most'. Those "
                            "two give 'total_paid' per group; 'category' only "
                            "gives 'food_total', because tax belongs to a whole "
                            "receipt and cannot be split between categories."
                        ),
                    },
                },
            },
        },
    },
]

# so agent.py can look the function up by the name the AI sent
TOOL_FUNCTIONS = {
    "find_purchases": find_purchases,
    "sum_expenses": sum_expenses,
}

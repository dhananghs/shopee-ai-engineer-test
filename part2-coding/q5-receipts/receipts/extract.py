# Sends the receipt photo to the AI and gets the shopping information back.
#
# OpenRouter speaks the same format as OpenAI, so we use the openai library
# and just point it at OpenRouter's address (see config/settings.py).

import base64
import json

from django.conf import settings
from openai import OpenAI

# The AI has to pick one of these for every item. Letting it invent its own
# words would break the "how much did I spend on drinks" question, because
# "drink", "beverage" and "Drinks" would all be counted separately.
#
# Only three, and deliberately so. The old list was full of things like
# "burger" and "pizza", which meant real Indonesian dishes - bakso, cah
# kangkung, cap jay - had nowhere to go and all landed in "other", making the
# category useless. Anything can be sorted into eaten, drunk, or neither, so
# these three are almost impossible to get wrong.
CATEGORIES = ["food", "beverage", "other"]

# What we want back. "strict" mode makes the AI follow this exactly, so we
# never have to guess whether a field is there or clean up broken JSON.
RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant": {
            "type": "string",
            "description": "Name of the shop or restaurant. Empty string if not readable.",
        },
        "bought_at": {
            "type": "string",
            "description": "Date on the receipt as YYYY-MM-DD. Empty string if not readable.",
        },
        "total": {
            "type": "number",
            "description": "Grand total actually paid, the big number at the bottom. 0 if not readable.",
        },
        "subtotal": {
            "type": "number",
            "description": "Sum of the food lines before any charges. 0 if not shown.",
        },
        "tax": {
            "type": "number",
            "description": "Tax, often written PPN or PB1. 0 if not shown.",
        },
        "service_charge": {
            "type": "number",
            "description": "Service charge. 0 if not shown.",
        },
        "delivery_fee": {
            "type": "number",
            "description": "Delivery or shipping fee. 0 if not shown.",
        },
        "discount": {
            "type": "number",
            "description": "Discount or promo, as a positive number. 0 if not shown.",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": CATEGORIES,
                        "description": (
                            "'food' for anything eaten, 'beverage' for anything "
                            "drunk, 'other' for anything else that was bought, "
                            "like a plastic bag or cigarettes."
                        ),
                    },
                    "quantity": {"type": "integer"},
                    "price": {
                        "type": "number",
                        "description": "Price for ONE of this item, no currency symbol.",
                    },
                },
                "required": ["name", "category", "quantity", "price"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "merchant", "bought_at", "total", "subtotal", "tax",
        "service_charge", "delivery_fee", "discount", "items",
    ],
    "additionalProperties": False,
}

# Note the last line. We deliberately do NOT ask for the customer name, phone
# number, address or card digits. If we asked, the AI would return them and
# they would end up in our database - which would defeat the whole point of
# throwing the photo away.
PROMPT = """You are reading a food receipt. Fill in the fields exactly as they
appear on the receipt.

Rules:
- Prices are numbers only. Remove "Rp", ".", "," and any currency wording.
  So "Rp 45.000" becomes 45000.
- "price" is the price of ONE item, not the line total. If the receipt shows
  "2x Cheeseburger  90.000" then quantity is 2 and price is 45000.
- The date must be YYYY-MM-DD. Receipts here are usually day/month/year, so
  20/06/2026 means 2026-06-20.
- "items" is everything the customer actually bought, one line each. Most will
  be food or drink, but a plastic bag, packaging, cigarettes or anything else
  bought is still an item - give those the category "other". Putting them in
  keeps the money adding up.
- Subtotal, tax, service charge, delivery fee and discount are NOT items.
  They are charges on the whole receipt and each has its own field.
- These should come out equal:
      subtotal + tax + service_charge + delivery_fee - discount = total
  If your numbers do not add up like that, read the receipt again.
- "discount" is a positive number even though it is money coming off.
- If something is blurry or missing, use an empty string for text and 0 for
  numbers. Do not invent values.
- Do NOT return the customer name, phone number, address, card number or
  order ID, even if you can see them on the receipt.
"""


def get_client():
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is empty. Put your key in the .env file."
        )
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def read_receipt(photo_bytes, content_type="image/jpeg"):
    """Give it the bytes of a photo, get back a dict with the shopping info."""

    client = get_client()

    # the picture has to be sent as text, so it gets base64 encoded and put
    # into a "data:" url. this is how the openai format takes images.
    encoded = base64.b64encode(photo_bytes).decode("ascii")
    data_url = "data:%s;base64,%s" % (content_type, encoded)

    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "receipt",
                "strict": True,
                "schema": RECEIPT_SCHEMA,
            },
        },
    )

    return json.loads(response.choices[0].message.content)

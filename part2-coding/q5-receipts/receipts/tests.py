import io
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from . import extract
from .insight import save_receipt
from .models import Receipt, ReceiptItem


def fake_image():
    """Makes a tiny picture in memory so the tests don't need a real file."""
    buf = io.BytesIO()
    Image.new("RGB", (60, 90), "white").save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")


# What the AI would have sent back. The tests use this instead of really
# calling the AI, because a test that goes out to the internet is slow, costs
# money every time it runs, and would fail in the build server where there is
# no api key.
FAKE_READING = {
    "merchant": "Warung Tegal Jaya",
    "bought_at": "2026-06-20",
    "total": 113220,
    "subtotal": 102000,
    "tax": 11220,
    "service_charge": 0,
    "delivery_fee": 0,
    "discount": 0,
    "items": [
        {"name": "Nasi Goreng Spesial", "category": "food", "quantity": 2, "price": 25000},
        {"name": "Ayam Geprek", "category": "food", "quantity": 1, "price": 28000},
        {"name": "Es Teh Manis", "category": "beverage", "quantity": 3, "price": 8000},
    ],
}


class UploadTest(TestCase):
    def test_home_page_opens(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    @patch("receipts.views.extract.read_receipt")
    def test_uploading_saves_a_receipt(self, fake_read):
        fake_read.return_value = FAKE_READING

        response = self.client.post("/", {"image": fake_image()})

        # after uploading we get sent to the detail page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(ReceiptItem.objects.count(), 3)

    @patch("receipts.views.extract.read_receipt")
    def test_nothing_is_saved_when_the_reading_fails(self, fake_read):
        """A half empty receipt in the list would be worse than none at all."""
        fake_read.side_effect = RuntimeError("the api is down")

        self.client.post("/", {"image": fake_image()})

        self.assertEqual(Receipt.objects.count(), 0)

    @patch("receipts.views.extract.read_receipt")
    def test_the_photo_is_not_kept_anywhere(self, fake_read):
        fake_read.return_value = FAKE_READING
        self.client.post("/", {"image": fake_image()})

        # there is no field on the model that could be holding the picture
        field_names = [f.name for f in Receipt._meta.get_fields()]
        self.assertNotIn("image", field_names)

    def test_detail_page_opens(self):
        receipt = Receipt.objects.create(merchant="KFC")
        response = self.client.get("/receipt/%d/" % receipt.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "KFC")


class ClientTest(TestCase):
    """Every other test swaps the AI call out for a fixed reading, which is
    what makes them fast and free - but it also means none of them ever build
    the real client, so a broken library combination sails through and only
    shows up when somebody uploads a receipt.

    That is exactly what happened: openai asks for "httpx<1", httpx 0.28
    dropped the "proxies" argument openai 1.30 still passes, and every upload
    failed with "Client.__init__() got an unexpected keyword argument
    'proxies'". This builds the client for real, without calling out to
    anything, so the versions are checked on every run."""

    @override_settings(OPENROUTER_API_KEY="not-a-real-key")
    def test_the_client_can_be_built(self):
        client = extract.get_client()
        self.assertIn("openrouter.ai", str(client.base_url))

    def test_a_missing_key_says_so_clearly(self):
        with override_settings(OPENROUTER_API_KEY=""):
            with self.assertRaises(RuntimeError):
                extract.get_client()


class ModelTest(TestCase):
    def test_line_total_multiplies_price_by_quantity(self):
        receipt = Receipt.objects.create()
        item = ReceiptItem.objects.create(receipt=receipt, name="Cheeseburger",
                                          quantity=2, price=45000)
        self.assertEqual(item.line_total(), 90000)

    def test_receipt_is_not_extracted_before_reading(self):
        receipt = Receipt.objects.create()
        self.assertFalse(receipt.is_extracted())


class InsightTest(TestCase):
    def test_insight_numbers_are_worked_out(self):
        receipt = save_receipt(FAKE_READING)

        self.assertEqual(receipt.item_count, 3)
        # by price of one item, so Ayam Geprek at 28000 beats the 25000 nasi
        self.assertEqual(receipt.most_expensive_item, "Ayam Geprek")
        # by money spent: food is 50000 + 28000, drinks only 3 x 8000
        self.assertEqual(receipt.top_category, "food")

    def test_a_broken_date_is_stored_as_nothing_rather_than_wrong(self):
        reading = dict(FAKE_READING, bought_at="not a date")
        receipt = save_receipt(reading)
        self.assertIsNone(receipt.bought_at)


class TaxTest(TestCase):
    """The food never adds up to what was actually paid, because of tax,
    service charge and delivery. These check the difference is accounted for
    instead of quietly disappearing."""

    def test_food_and_paid_are_different_numbers(self):
        receipt = save_receipt(FAKE_READING)

        self.assertEqual(receipt.items_total(), 102000)   # just the food
        self.assertEqual(receipt.total, 113220)           # what was paid
        self.assertEqual(receipt.charges(), 11220)        # the tax

    def test_the_numbers_add_up(self):
        receipt = save_receipt(FAKE_READING)
        self.assertEqual(receipt.difference(), 0)
        self.assertTrue(receipt.adds_up())

    def test_a_missed_line_is_noticed(self):
        """If the AI misses a charge the total will not match, and we want to
        say so on the page rather than show numbers that disagree."""
        reading = dict(FAKE_READING, tax=0)
        receipt = save_receipt(reading)

        self.assertFalse(receipt.adds_up())
        self.assertEqual(receipt.difference(), 11220)

    def test_discount_comes_off_and_delivery_goes_on(self):
        reading = dict(FAKE_READING, tax=10000, delivery_fee=15000,
                       discount=5000, total=122000)
        receipt = save_receipt(reading)

        # 10000 + 15000 - 5000
        self.assertEqual(receipt.charges(), 20000)
        # 102000 + 20000
        self.assertTrue(receipt.adds_up())

    def test_missing_total_is_worked_out_including_the_charges(self):
        reading = dict(FAKE_READING, total=0)
        receipt = save_receipt(reading)
        # food 102000 + tax 11220, not just the food
        self.assertEqual(receipt.total, 113220)

from django.db import models


class Receipt(models.Model):
    """What was read off one receipt photo.

    The photo itself is NOT kept. It is read once while the upload request is
    still running and then thrown away, so a receipt (which has someone's name
    and card digits on it) never gets written to disk or into the database.
    Only the shopping information below is stored.
    """

    uploaded_at = models.DateTimeField(auto_now_add=True)

    # these three get filled in by extract.py after the AI reads the picture.
    # they are allowed to be empty because the upload happens first and the
    # reading happens after.
    merchant = models.CharField(max_length=200, blank=True)
    bought_at = models.DateField(null=True, blank=True, db_index=True)

    # what was actually paid, the big number at the bottom of the receipt
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # the extra charges. these are NOT food so they are not ReceiptItem rows,
    # but they are real money and without them the food adds up to less than
    # what was paid.
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # the insight bits. we work these out ourselves in python, NOT with the AI,
    # because adding up numbers is something a database does correctly every
    # time and a language model does not.
    item_count = models.IntegerField(default=0)
    most_expensive_item = models.CharField(max_length=200, blank=True)
    top_category = models.CharField(max_length=50, blank=True)

    # exactly what the AI sent back. kept so that when something comes out
    # wrong you can look at the original answer instead of guessing.
    raw_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        if self.merchant:
            return "%s (%s)" % (self.merchant, self.bought_at)
        return "receipt #%s (not read yet)" % self.pk

    def is_extracted(self):
        # used by the template to decide whether to show the items table
        return self.item_count > 0

    def items_total(self):
        """Just the food, no charges."""
        return sum(item.line_total() for item in self.items.all())

    def charges(self):
        """Everything that was paid on top of the food."""
        return self.tax + self.service_charge + self.delivery_fee - self.discount

    def difference(self):
        """How far off the sums are from the total printed on the receipt.

        Should be 0. If it is not, the AI most likely missed a line, so this
        is worth showing on the page instead of hiding it.
        """
        if self.total is None:
            return 0
        return self.total - (self.items_total() + self.charges())

    def adds_up(self):
        # small gaps are normal, receipts round to the nearest rupiah
        return abs(self.difference()) <= 1


class ReceiptItem(models.Model):
    """One line on a receipt, e.g. "Cheeseburger x2  90000"."""

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, blank=True)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name

    def line_total(self):
        return self.price * self.quantity

from datetime import date, timedelta

from django.test import TestCase

from receipts.models import Receipt, ReceiptItem

from .tools import clean_category, find_purchases, sum_expenses


def make_receipt(merchant, days_ago, items, tax=0, delivery_fee=0):
    food = sum(price * quantity for _, _, quantity, price in items)
    receipt = Receipt.objects.create(
        merchant=merchant,
        bought_at=date.today() - timedelta(days=days_ago),
        tax=tax,
        delivery_fee=delivery_fee,
        total=food + tax + delivery_fee,
    )
    for name, category, quantity, price in items:
        ReceiptItem.objects.create(receipt=receipt, name=name, category=category,
                                   quantity=quantity, price=price)
    return receipt


class ToolTest(TestCase):
    def setUp(self):
        make_receipt("McDonalds Senayan", 1, [
            ("Big Mac", "food", 1, 48000),
            ("Coca Cola Medium", "beverage", 1, 18000),
        ], tax=7260, delivery_fee=15000)
        make_receipt("Burger King Plaza", 3, [
            ("Whopper", "food", 1, 55000),
        ])
        make_receipt("KFC Kemang", 30, [
            ("Fried Chicken 2pcs", "food", 2, 38000),
        ])

    def today(self):
        return date.today().isoformat()

    def days_ago(self, n):
        return (date.today() - timedelta(days=n)).isoformat()

    def test_finds_only_what_is_inside_the_dates(self):
        rows = find_purchases(date_from=self.days_ago(7), date_to=self.today())
        names = [r["item"] for r in rows]

        self.assertIn("Big Mac", names)
        self.assertIn("Whopper", names)
        # the KFC one was a month ago so it must not show up
        self.assertNotIn("Fried Chicken 2pcs", names)

    def test_hamburger_finds_a_whopper_and_a_big_mac(self):
        """The whole reason item_terms is a list. Neither "Whopper" nor
        "Big Mac" contains the word hamburger, so searching for the one word
        the user typed would find neither of them. These are the words the AI
        really sends for "hamburger"."""
        rows = find_purchases(
            item_terms=["hamburger", "burger", "cheeseburger", "whopper", "big mac"]
        )
        names = [r["item"] for r in rows]

        self.assertIn("Whopper", names)
        self.assertIn("Big Mac", names)
        self.assertNotIn("Coca Cola Medium", names)

    def test_food_total_is_price_times_quantity(self):
        result = sum_expenses()
        # 48000 + 18000 + 55000 + (2 x 38000)
        self.assertEqual(result["food_total"], 197000)

    def test_total_can_be_limited_to_one_category(self):
        result = sum_expenses(category="beverage")
        self.assertEqual(result["food_total"], 18000)

    def test_plural_category_still_works(self):
        """The AI keeps sending "drinks" while the database says "drink".
        Before this was handled the user was told they spent zero."""
        self.assertEqual(clean_category("beverages"), "beverage")
        self.assertEqual(clean_category("Beverages"), "beverage")
        self.assertEqual(clean_category("beverage"), "beverage")

        result = sum_expenses(category="beverages")
        self.assertEqual(result["food_total"], 18000)

    def test_grouping_by_shop_gives_what_was_really_paid(self):
        rows = sum_expenses(group_by="merchant")
        paid = {r["group"]: r["total_paid"] for r in rows}
        food = {r["group"]: r["food_total"] for r in rows}

        # McDonalds had tax and delivery on top of the food
        self.assertEqual(food["McDonalds Senayan"], 66000)
        self.assertEqual(paid["McDonalds Senayan"], 88260)
        # Burger King had neither, so the two match
        self.assertEqual(paid["Burger King Plaza"], 55000)

    def test_biggest_spending_day_counts_the_tax(self):
        """Without this the busiest day is worked out from the food only, so
        a day with a big delivery fee can be ranked too low."""
        rows = sum_expenses(group_by="day")

        # McDonalds day: 66000 food but 88260 actually paid, which beats the
        # 55000 Burger King day even though both look close on food alone
        self.assertEqual(rows[0]["total_paid"], 88260)
        self.assertGreater(rows[0]["total_paid"], rows[0]["food_total"])

    def test_grouping_by_category_has_no_paid_figure(self):
        rows = sum_expenses(group_by="category")
        for row in rows:
            self.assertIn("food_total", row)
            self.assertNotIn("total_paid", row)

    def test_nothing_found_gives_zero_not_an_error(self):
        result = sum_expenses(category="other")
        self.assertEqual(result["food_total"], 0)
        self.assertEqual(result["number_of_items"], 0)

    def test_paid_is_bigger_than_the_food_because_of_tax(self):
        """The thing that started all this - the food never adds up to what
        actually left the wallet."""
        result = sum_expenses(merchant="McDonalds")

        self.assertEqual(result["food_total"], 66000)          # 48000 + 18000
        self.assertEqual(result["total_paid"], 88260)          # + 7260 tax + 15000 delivery
        self.assertEqual(result["extra_charges"], 22260)

    def test_no_paid_figure_when_asking_about_one_category(self):
        """Tax belongs to the whole receipt, so it cannot honestly be split
        between kinds of food. Better to leave it out than to guess."""
        result = sum_expenses(category="beverage")
        self.assertNotIn("total_paid", result)

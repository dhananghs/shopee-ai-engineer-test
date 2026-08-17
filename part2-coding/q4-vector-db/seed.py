# fills the items table with some food so there is something to search.
# food and not the customers csv because question 5 is about food receipts,
# so this data carries over.
#
# usage: python seed.py

import vector_store
from vectorizer import vectorize

# name, category, merchant, price
ITEMS = [
    ("Cheeseburger",              "burger",   "Burger King",      45000),
    ("Double Cheeseburger",       "burger",   "Burger King",      65000),
    ("Whopper",                   "burger",   "Burger King",      55000),
    ("Big Mac",                   "burger",   "McDonalds",        48000),
    ("Beef Burger Deluxe",        "burger",   "Wendys",           52000),
    ("Chicken Burger",            "burger",   "McDonalds",        40000),
    ("Veggie Burger",             "burger",   "Burgreens",        43000),

    ("Fried Chicken 2pcs",        "chicken",  "KFC",              38000),
    ("Spicy Fried Chicken",       "chicken",  "KFC",              40000),
    ("Chicken Wings 6pcs",        "chicken",  "Wingstop",         62000),
    ("Grilled Chicken Rice",      "chicken",  "HokBen",           35000),
    ("Chicken Katsu",             "chicken",  "HokBen",           37000),
    ("Ayam Geprek",               "chicken",  "Geprek Bensu",     28000),

    ("Nasi Goreng Spesial",       "rice",     "Warung Tegal",     25000),
    ("Nasi Padang",               "rice",     "RM Sederhana",     32000),
    ("Chicken Fried Rice",        "rice",     "Warung Tegal",     27000),
    ("Beef Teriyaki Rice Bowl",   "rice",     "Yoshinoya",        45000),

    ("Mie Ayam Bakso",            "noodle",   "Mie Gacoan",       22000),
    ("Ramen Tonkotsu",            "noodle",   "Ichiran",          75000),
    ("Spaghetti Bolognese",       "noodle",   "Pizza Hut",        58000),
    ("Pad Thai",                  "noodle",   "Thai Express",     52000),

    ("Pepperoni Pizza Large",     "pizza",    "Pizza Hut",        120000),
    ("Cheese Pizza Medium",       "pizza",    "Dominos",          89000),
    ("Meat Lovers Pizza",         "pizza",    "Dominos",          135000),

    ("French Fries Large",        "side",     "McDonalds",        25000),
    ("Onion Rings",               "side",     "Burger King",      27000),
    ("Potato Wedges",             "side",     "KFC",              23000),
    ("Garlic Bread",              "side",     "Pizza Hut",        30000),

    ("Iced Lemon Tea",            "drink",    "McDonalds",        15000),
    ("Es Teh Manis",              "drink",    "Warung Tegal",      8000),
    ("Iced Coffee Latte",         "drink",    "Starbucks",        45000),
    ("Cappuccino",                "drink",    "Starbucks",        42000),
    ("Coca Cola Medium",          "drink",    "McDonalds",        18000),
    ("Fresh Orange Juice",        "drink",    "Juice Bar",        28000),

    ("Chocolate Sundae",          "dessert",  "McDonalds",        18000),
    ("Cheesecake Slice",          "dessert",  "Starbucks",        48000),
    ("Martabak Manis Coklat",     "dessert",  "Martabak 88",      65000),
    ("Vanilla Ice Cream",         "dessert",  "Baskin Robbins",   35000),

    ("Caesar Salad",              "salad",    "SaladStop",        55000),
    ("Greek Salad",               "salad",    "SaladStop",        58000),
]


def main():
    conn = vector_store.connect()
    cur = conn.cursor()

    # wipe first so running seed.py twice doesn't give duplicate rows.
    # TRUNCATE also resets the id counter back to 1, DELETE doesn't.
    cur.execute("TRUNCATE items RESTART IDENTITY")

    for name, category, merchant, price in ITEMS:
        # embed the name plus the category, that way searching "burger" still
        # finds "Whopper" and "Big Mac" which don't have the word in them
        text = name + " " + category
        insert_vec = vectorize(text)
        vector_store.insert_item(cur, name, category, merchant, price, insert_vec)

    conn.commit()
    print("inserted", vector_store.count_items(cur), "items")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

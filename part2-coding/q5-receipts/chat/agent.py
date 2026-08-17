# Runs the conversation with the AI.
#
# How one question works:
#   1. we send the question plus the list of tools
#   2. the AI answers "call sum_expenses with these dates"
#   3. we run that function ourselves and send the rows back
#   4. the AI turns the rows into a sentence
#
# So the AI does the understanding and the wording. The looking up and the
# adding up is done by our own code in tools.py.

import json
from datetime import date

from django.conf import settings
from openai import OpenAI

from .tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

# how many times round the loop before we give up. stops a broken conversation
# from calling the AI forever.
MAX_STEPS = 5


def build_system_prompt():
    # The AI has no clock. Without being told today's date it cannot work out
    # what "yesterday" means and will guess, usually wrongly.
    today = date.today()

    return """You answer questions about food receipts the user has uploaded.

Today is %s (%s).

Working out dates:
- "yesterday" means %s
- "last 7 days" means %s to %s
- A date with no year, like "20 June", means the most recent one that has
  already happened, not a future date.
- Always pass dates as YYYY-MM-DD.

Rules:
- Always call a tool before you answer. You cannot see the receipts yourself,
  so answering without calling a tool means guessing.
- Never ask the user to narrow the question down. Make the sensible assumption
  and call the tool. "Food" on its own means all food, so leave category out.
- Never add up prices yourself. Call sum_expenses and use the number it gives
  back, even for simple sums.
- sum_expenses gives two numbers. "total_paid" is what actually left the
  wallet, tax and delivery included - use that one for "how much did I spend".
  "food_total" is the food on its own. If they are different, give the paid
  figure and mention the extra briefly, for example "Rp113,220 including
  Rp11,220 tax and fees".
- When the question is about one kind of food there is no "total_paid",
  because tax cannot be split between kinds of food. Use "food_total" and
  do not pretend it includes tax.
- sum_expenses also gives "tax", "delivery_fee", "service_charge" and
  "discount" separately. When asked about one of them, quote that number.
  "extra_charges" is all of them added together with the discount taken off,
  so do not call it "tax" or "delivery" on its own.
- For "which day did I spend most" or "which shop do I spend most at", use
  group_by "day" or "merchant". Each group comes back with "total_paid" and
  "food_total" - answer with "total_paid", the same as for any other
  spending question. Grouping by category only gives "food_total".
- For "most expensive" or "cheapest", call find_purchases without item_terms
  and pick the row with the biggest or smallest price out of what comes back.
- When looking for a kind of food, send several related words in item_terms,
  because receipts use brand names. A "Whopper" is a hamburger.
- Answer in one or two short friendly sentences. Include the amounts and the
  shop names. Write money like Rp55,000.
- Reply in the language the user asked in.
- If the tools come back with nothing, say plainly that there is nothing in
  the receipts about it. Never invent a receipt, a shop or an amount.
""" % (
        today.isoformat(),
        today.strftime("%A"),
        (today.fromordinal(today.toordinal() - 1)).isoformat(),
        (today.fromordinal(today.toordinal() - 6)).isoformat(),
        today.isoformat(),
    )


def get_client():
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is empty. Put your key in the .env file."
        )
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def run_tool(name, arguments):
    """Runs one of our own functions and gives back whatever it returned."""
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": "there is no tool called %s" % name}
    return function(**arguments)


def answer(question):
    client = get_client()

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": question},
    ]

    for step in range(MAX_STEPS):
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        reply = response.choices[0].message

        # no tool wanted means the AI is done and this is the real answer
        if not reply.tool_calls:
            if reply.content:
                return reply.content

            # sometimes it sends back an empty message even though the rows it
            # asked for are sitting right there. ask it again rather than
            # showing the user a blank answer.
            messages.append({
                "role": "user",
                "content": "Answer the question in words, using the information above.",
            })
            continue

        # remember what the AI asked for, it has to stay in the conversation
        messages.append({
            "role": "assistant",
            "content": reply.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in reply.tool_calls
            ],
        })

        # the AI can ask for more than one thing at once, so do them all
        for call in reply.tool_calls:
            arguments = json.loads(call.function.arguments or "{}")
            result = run_tool(call.function.name, arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    return "Sorry, I could not work that out."

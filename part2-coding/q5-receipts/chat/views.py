from django.shortcuts import redirect, render

from . import agent
from .models import Question


def ask(request):
    """The question page. Asks the AI and shows what it said."""

    if request.method == "POST":
        text = request.POST.get("question", "").strip()
        if text:
            question = Question(question=text)
            try:
                question.answer = agent.answer(text)
            except Exception as problem:
                # show the problem on the page instead of a django error page,
                # so a missing api key or a network hiccup is obvious
                question.answer = "Something went wrong: %s" % problem
            question.save()
        return redirect("ask")

    return render(request, "chat/ask.html", {
        "questions": Question.objects.all()[:20],
    })

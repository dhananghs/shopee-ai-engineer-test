from django.db import models


class Question(models.Model):
    """Keeps what the user asked and what the AI answered, so the chat page
    still shows something after you refresh it."""

    question = models.TextField()
    answer = models.TextField(blank=True)
    asked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asked_at"]

    def __str__(self):
        return self.question[:60]

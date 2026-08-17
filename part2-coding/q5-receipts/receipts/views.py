import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from . import extract, insight
from .forms import UploadForm
from .models import Receipt


def save_debug_copy(photo_bytes, filename):
    """Only used while checking that the reading works. Normally switched off,
    see KEEP_RECEIPT_IMAGE in the .env file."""
    folder = os.path.join(settings.MEDIA_ROOT, "debug")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), "wb") as f:
        f.write(photo_bytes)


def upload(request):
    """Home page. Shows the upload box and the receipts read so far."""

    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.cleaned_data["image"]

            # read the whole picture into memory. this is the only place the
            # picture exists - once this function finishes python throws it
            # away and it was never written to disk.
            photo_bytes = photo.read()

            if settings.KEEP_RECEIPT_IMAGE:
                save_debug_copy(photo_bytes, photo.name)

            # if the AI call fails we save nothing at all and send the user
            # back to try again. saving a half empty receipt would be worse
            # than saving none, because it would sit in the list forever
            # pretending to be a real one.
            try:
                data = extract.read_receipt(photo_bytes, photo.content_type)
            except Exception as problem:
                messages.error(request, "Could not read that receipt: %s" % problem)
                return redirect("upload")

            receipt = insight.save_receipt(data)
            messages.success(request, "Receipt read. The photo was not saved.")
            return redirect("detail", pk=receipt.pk)
    else:
        form = UploadForm()

    return render(request, "receipts/upload.html", {
        "form": form,
        "receipts": Receipt.objects.all()[:20],
    })


def detail(request, pk):
    """Shows what was read off one receipt, plus the insight."""

    receipt = get_object_or_404(Receipt, pk=pk)
    return render(request, "receipts/detail.html", {"receipt": receipt})

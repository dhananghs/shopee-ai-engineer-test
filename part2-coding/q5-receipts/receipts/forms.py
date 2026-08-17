from django import forms


class UploadForm(forms.Form):
    """Just a file box. It is NOT a ModelForm on purpose - a ModelForm would
    save the picture into a folder, and we don't want to keep the picture."""

    image = forms.ImageField(label="Receipt photo")

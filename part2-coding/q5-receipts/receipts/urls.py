from django.urls import path

from . import views

urlpatterns = [
    path("", views.upload, name="upload"),
    path("receipt/<int:pk>/", views.detail, name="detail"),
]

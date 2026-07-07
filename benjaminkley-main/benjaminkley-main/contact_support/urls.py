from django.urls import path
from .views import SubmitContactMessageView

urlpatterns = [
    path('submit/', SubmitContactMessageView.as_view(), name='submit-contact-message'),
]
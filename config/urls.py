from django.urls import path

from api.views import RouteView

urlpatterns = [
    path("api/route/", RouteView.as_view()),
]

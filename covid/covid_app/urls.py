from django.urls import path

from . import views

app_name = "covid_app"

urlpatterns = [
    path('', views.index, name='index'),
    path('clear_db/', views.clear_db, name='clear_db'),
]

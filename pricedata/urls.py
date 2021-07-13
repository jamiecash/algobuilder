from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import path, register_converter
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic import RedirectView

from . import views, converters

register_converter(converters.DatetimeConverter, 'datetime')
register_converter(converters.ListOfStringsConverter, 'listofstr')

app_name = 'pricedata'

urlpatterns = [
    path('', views.index, name='index'),

    # Data quality dashboard
    path('quality/', views.quality, name='quality'),
]

urlpatterns += staticfiles_urlpatterns()

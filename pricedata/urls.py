from django.urls import path, register_converter
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from . import converters, views

register_converter(converters.DatetimeConverter, 'datetime')
register_converter(converters.ListOfStringsConverter, 'listofstr')

app_name = 'pricedata'

urlpatterns = [
    path('', views.IndexView.as_view(), name="index"),

    # Data metrics, quality dashboard and candles
    path('metrics/', views.MetricsView.as_view(), name='metrics'),
    path('quality/', views.QualityView.as_view(), name='quality'),
    path('candles/', views.CandlesView.as_view(), name='candles'),
]

urlpatterns += staticfiles_urlpatterns()

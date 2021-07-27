from django.urls import path, register_converter
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from . import views
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

    # A test page for development. TODO Remove this, test.html and TestView
    path('test/', views.TestView.as_view(), name="test"),
]

urlpatterns += staticfiles_urlpatterns()

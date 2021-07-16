from django.urls import path, register_converter
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from . import views
from . import converters
from .views import IndexView, QualityView, TestView

register_converter(converters.DatetimeConverter, 'datetime')
register_converter(converters.ListOfStringsConverter, 'listofstr')

app_name = 'pricedata'

urlpatterns = [
    path('', IndexView.as_view(), name="index"),

    # Data quality dashboard
    path('quality/', QualityView.as_view(), name='quality'),

    # A test page for development. TODO Remove this, test.html and TestView
    path('test/', TestView.as_view(), name="test"),
]

urlpatterns += staticfiles_urlpatterns()

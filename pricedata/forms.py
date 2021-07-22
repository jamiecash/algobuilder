from collections import Counter
from datetime import timedelta

from django import forms
from django.forms import DateTimeInput
from django.utils import timezone

from pricedata import models
from pricedata.widgets import BootstrapDateTimePickerInput


class PriceDataQualityForm(forms.Form):
    # Data for selects
    datasources = [ds.name for ds in models.DataSource.objects.all()]
    periods = [dscp.period for dscp in models.DataSourceCandlePeriod.objects.filter(datasource__name__in=datasources)]
    aggregation_periods = ['minutes', 'hours', 'days', 'weeks', 'months']

    # Create the form. This is a data intensive view and will take a long time to load. We will not allow the user to
    # select most parameters but will control through sensible defaults and zooming in on the chart.

    # From and to dates.
    from_date = forms.DateTimeField(label="From date", input_formats=['%d/%m/%Y %H:%M'],
                                    widget=DateTimeInput(attrs={'class': 'form-control', 'readonly': True}))

    to_date = forms.DateTimeField(label="To date", input_formats=['%d/%m/%Y %H:%M'],
                                  widget=DateTimeInput(attrs={'class': 'form-control', 'readonly': True}))

    # Data sources.
    data_sources = forms.MultipleChoiceField(label="Data sources", required=True,
                                             widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
                                             choices=[(ch, ch) for ch in datasources])

    # Candle period. User can select from all available candle periods for datasources.
    candle_period = \
        forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-control'}), required=True,
                          choices=[(period, period) for period in periods],
                          label="Candle period")

    # Aggregation period.
    aggregation_period = \
        forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
                        required=True, label="Aggregation period")


from collections import Counter
from datetime import timedelta

from django import forms
from django.utils import timezone

from pricedata import models
from pricedata.widgets import BootstrapDateTimePickerInput


class PriceDataQualityForm(forms.Form):
    # From date will be  approx 500 plots from now. Actual date will depend on candle_period
    nplt = 500

    # Some data we need to calculate default values
    timedeltas = {
        '1S': timedelta(seconds=1 * nplt), '5S': timedelta(seconds=5 * nplt), '10S': timedelta(seconds=10 * nplt),
        '15S': timedelta(seconds=15 * nplt), '30S': timedelta(seconds=30 * nplt), '1M': timedelta(minutes=1 * nplt),
        '5M': timedelta(minutes=5 * nplt), '10M': timedelta(minutes=10 * nplt), '15M': timedelta(minutes=15 * nplt),
        '30M': timedelta(minutes=30 * nplt), '1H': timedelta(hours=1 * nplt), '3H': timedelta(hours=3 * nplt),
        '6H': timedelta(hours=6 * nplt), '12H': timedelta(hours=12 * nplt), '1D': timedelta(days=1 * nplt),
        '1W': timedelta(days=7 * nplt), '1MO': timedelta(days=28 * nplt)
    }

    datasources = [ds.name for ds in models.DataSource.objects.all()]
    periods = [dscp.period for dscp in models.DataSourceCandlePeriod.objects.filter(datasource__name__in=datasources)]
    most_used_period = '1S' if len(periods) == 0 else Counter(periods).most_common(1)[0][0]

    now = timezone.now()
    frm = now - timedeltas[most_used_period]

    # Create the form.

    # From date. Default is approx 500 plots from now.
    from_date = forms.DateTimeField(label="From date", input_formats=['%d/%m/%Y %H:%M'],
                                    widget=BootstrapDateTimePickerInput, initial=frm)

    # To Date default is now
    to_date = forms.DateTimeField(label="To date", input_formats=['%d/%m/%Y %H:%M'],
                                  widget=BootstrapDateTimePickerInput, initial=now)

    # Data sources. User can select from all configured data sources
    data_sources = forms.MultipleChoiceField(label="Data sources", widget=forms.CheckboxSelectMultiple, required=True,
                                             choices=[(ch, ch) for ch in datasources], initial=True)

    # Candle period. User can select from all available candle periods for datasources. Default is candle period
    # configured for most data sources
    candle_period = forms.ChoiceField(label="Candle period", widget=forms.RadioSelect, required=True,
                                      choices=[(period, period) for period in periods], initial=most_used_period)

    # Aggregation period. None selected
    aggregation_period = \
        forms.ChoiceField(widget=forms.RadioSelect, required=True,
                          choices=[(ch, ch) for ch in ['minutes', 'hours', 'days', 'weeks', 'months']],
                          label="Aggregation period")




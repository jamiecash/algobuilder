from django import forms
from django.forms import DateTimeInput
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
    datasources = forms.MultipleChoiceField(label="Data sources", required=True,
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


class PriceDataMetricsForm(forms.Form):
    # Data for selects
    datasources = [ds.name for ds in models.DataSource.objects.all()]
    periods = [dscp.period for dscp in models.DataSourceCandlePeriod.objects.filter(datasource__name__in=datasources)]

    # Data source.
    datasource = forms.ChoiceField(label="Data source", required=True,
                                   widget=forms.Select(attrs={'class': 'form-control'}),
                                   choices=[('all', 'All')] + [(ch, ch) for ch in datasources])

    # Period
    candle_period = \
        forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-control'}), required=True,
                          choices=[(period, period) for period in periods],
                          label="Candle period")


class PriceDataCandleForm(forms.Form):
    # Data for selects
    dscps = [dscp for dscp in models.DataSourceCandlePeriod.objects.all()]
    symbols = [dss.symbol.name for dss in models.DataSourceSymbol.objects.filter(retrieve_price_data=True)]

    # Data source periods.
    datasource_period = forms.ChoiceField(label="Data source / Period", required=True,
                                          widget=forms.Select(attrs={'class': 'form-control'}),
                                          choices=[(dscp.id, f'{dscp.datasource.name} {dscp.period}')
                                                   for dscp in dscps])
    # From and to dates
    from_date = forms.DateTimeField(label="From date", input_formats=['%d/%m/%Y %H:%M'],
                                    widget=BootstrapDateTimePickerInput(attrs={'class': 'form-control'}))

    to_date = forms.DateTimeField(label="To date", input_formats=['%d/%m/%Y %H:%M'],
                                  widget=BootstrapDateTimePickerInput(attrs={'class': 'form-control'}))

    # Symbol.
    # TODO Ajax to get only symbols for the selected datasource and period.Guide here:
    #  https://simpleisbetterthancomplex.com/tutorial/2018/01/29/how-to-implement-dependent-or-chained-dropdown-list-with-django.html
    symbol = \
        forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-control'}), required=True,
                          choices=[(symbol, symbol) for symbol in symbols],
                          label="Symbol")

    # Bid or ask
    bid_ask = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-control'}), required=True,
                                choices=[('bid', 'Bid'), ('ask', 'Ask')],
                                label="Price Type")

    # Candles or bars
    chart_type = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-control'}), required=True,
                                   choices=[('candle', 'OHLC Candle'),  ('bar', 'OHLC Bar')],
                                   label="Chart Type")

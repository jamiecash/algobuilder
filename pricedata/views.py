from collections import Counter
from datetime import timedelta
from typing import List

import pandas as pd
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template import loader
from django.utils import timezone

from pricedata import models
from pricedata.forms import PriceDataQualityForm


def index(request):
    return render(request, 'pricedata/index.html', {})


# Create your views here.
def quality(request):
    """
    The data quality scatter plot
    :param request:

    The populated form will be retrieved from the request.POST and will contain the following values:
    * from_date: The from date for the chart.
    * to_date: The from date for the chart.
    * data_sources: List of datasource names to include.
    * candle_period: The candle period to assess.
    * aggregation_period: 'minutes', 'hours', 'days', 'weeks', or 'months'. Will aggregate plots to period and
        colour for count of values. If not supplied, then there will be a plot for every data point.

        The period cannot be less than the candle period that the price data was retrieved for, i.e., if price data is
        daily candles [1D], then period must be 'days', 'weeks' or 'months'. It cannot be 'minutes' or 'hours'.

        Colouring will use the following chart colour scales from bad to good for 1 second data:
            'minutes': 0-60, where 0 is there is no data and 60 is there is data for every second
            'hours': 0-1440, where 0 is there is no data and 1440 is there is data for every second
            'days': 0-34560, where 0 is there is no data and 34560 is there is data for every second
            'weeks': 0-241920, where 0 is there is no data and 241920 is there is data for every second
            'months': 0-967680, where 0 is there is no data and 967680 is there is data for every second

            Note: months is assessed against 28 days worth of data.

        For other candle periods, the range end is the max number of prices for the period.

    The chart shows indicative data quality based on data being available for every possible candle period. This is
    not realistic due to market open / close, weekends, holidays, so it is not expected that the top end of the
    scale will not be possible. The chart should be used to compare quality at different dates / times.

    :return: the rendered form / data page
    """

    # Data to display. Default is empty. Will be populated when form is submitted
    data = []

    # If the form is get, then we are displaying for the first time, just show the form with no data. Otherwise
    # process the form and get the data
    if request.method == 'GET':
        form = PriceDataQualityForm()
    else:
        # create a form instance and populate it with data from the request:
        form = PriceDataQualityForm(request.POST)

        # check whether it's valid:
        if form.is_valid():
            # It is valid. Get the cleaned parameters and get the data
            from_date = form.cleaned_data['from_date']
            to_date = form.cleaned_data['to_date']
            data_sources = form.cleaned_data['data_sources']
            candle_period = form.cleaned_data['candle_period']

            for ds in data_sources:
                price_data = models.Candle.objects.filter(datasource_symbol__datasource__name=ds,
                                                          time__gte=from_date, time__lte=to_date, period=candle_period)

                # convert to dataframe
                df = pd.DataFrame(list(price_data.values('datasource_symbol__symbol__name', 'time')))

                # TODO Create aggregate data

                # Add the dataframes to the data
                data.append(df)

    # Populate context with form and data and render
    context = {
        'form': form,
        'data': data
    }

    return render(request, 'pricedata/quality.html', context)


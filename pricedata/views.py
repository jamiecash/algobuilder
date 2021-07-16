from collections import Counter
from datetime import timedelta
import time
from typing import List, Dict

import pandas as pd
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from pricedata import models
from pricedata.forms import PriceDataQualityForm


class IndexView(View):
    form_class = None
    template_name = "pricedata/index.html"

    def get(self, request):
        return render(self.request, self.template_name, {})

    def post(self, request):
        return HttpResponse("POST not supported", status=404)


class TestView(View):
    form_class = None
    template_name = "pricedata/test.html"

    def get(self, request):
        chartdata = [{'name': 'Jan', 'data': [[12, 100], [13, 21]]}, {'name': 'Feb', 'data': [[12, 100], [13, 21]]}]

        return render(self.request, self.template_name, {'chartdata': chartdata})

    def post(self, request):
        return HttpResponse("POST not supported", status=404)


class QualityView(View):
    """
    The data quality scatter plot

    The populated form will be retrieved from the request.POST and will contain the following values:

    """

    form_class = PriceDataQualityForm
    template_name = 'pricedata/quality.html'

    def get(self, request):
        # Get chart data for initial values
        chart_data = QualityView.get_chart_data(self.initial)

        return render(self.request, self.template_name, {'form': self.form_class(initial=self.initial),
                                                         'data': chart_data})

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Get chart data
            chart_data = QualityView.get_chart_data(form.cleaned_data)

            return render(self.request, self.template_name, {'form': self.form_class, 'data': chart_data})
        else:
            return HttpResponse("Invalid form", status=404)

    @property
    def initial(self) -> Dict:
        """
        Gets the initial values for the form
        :return: Dict of initial values
        """
        initial = {}

        # From date will be  approx 500 plots from now. Actual date will depend on candle_period
        nplt = 500
        timedeltas = {
            '1S': timedelta(seconds=1 * nplt), '5S': timedelta(seconds=5 * nplt), '10S': timedelta(seconds=10 * nplt),
            '15S': timedelta(seconds=15 * nplt), '30S': timedelta(seconds=30 * nplt), '1M': timedelta(minutes=1 * nplt),
            '5M': timedelta(minutes=5 * nplt), '10M': timedelta(minutes=10 * nplt), '15M': timedelta(minutes=15 * nplt),
            '30M': timedelta(minutes=30 * nplt), '1H': timedelta(hours=1 * nplt), '3H': timedelta(hours=3 * nplt),
            '6H': timedelta(hours=6 * nplt), '12H': timedelta(hours=12 * nplt), '1D': timedelta(days=1 * nplt),
            '1W': timedelta(days=7 * nplt), '1MO': timedelta(days=28 * nplt)
        }

        datasources = [ds.name for ds in models.DataSource.objects.all()]
        periods = [dscp.period for dscp in
                   models.DataSourceCandlePeriod.objects.filter(datasource__name__in=datasources)]
        most_used_period = '1S' if len(periods) == 0 else Counter(periods).most_common(1)[0][0]

        initial['to_date'] = timezone.now()
        initial['from_date'] = initial['to_date'] - timedeltas[most_used_period]
        initial['data_sources'] = datasources
        initial['candle_period'] = most_used_period
        initial['aggregation_period'] = 'minutes'

        return initial

    @staticmethod
    def get_chart_data(params: Dict) -> Dict[str, List]:
        """
        Gets the chart data
        :param params: Dict containing:
            from_date: The from date for the chart.
            to_date: The from date for the chart.
            data_sources: List of datasource names to include.
            candle_period: The candle period to assess.
            aggregation_period: 'minutes', 'hours', 'days', 'weeks', or 'months'. Will aggregate plots to period and
                colour for count of values. This cannot be less than the candle period that the price data was
                retrieved for, i.e., if price data is daily candles [1D], then period must be 'days', 'weeks' or
                'months'. It cannot be 'minutes' or 'hours'. Colouring will use the following chart colour scales from
                bad to good for 1 second data:
                    'minutes': 0-60, where 0 is there is no data and 60 is there is data for every second
                    'hours': 0-1440, where 0 is there is no data and 1440 is there is data for every second
                    'days': 0-34560, where 0 is there is no data and 34560 is there is data for every second
                    'weeks': 0-241920, where 0 is there is no data and 241920 is there is data for every second
                    'months': 0-967680, where 0 is there is no data and 967680 is there is data for every second

                Note: months is assessed against 28 days worth of data. For other candle periods, the range end is the
                max number of prices for the period.

        The chart shows indicative data quality based on data being available for every possible candle period. This is
        not realistic due to market open / close, weekends, holidays, so it is not expected that the top end of the
        scale will not be possible. The chart should be used to compare quality at different dates / times and across
        different datasources.

        :return: Dict containing datasource name and its chart data. Chart data should contain 3 columns for plotting:
            x; y; & z.
        """
        chart_data = {}

        # Max values for each aggregation_period
        maxagg = {'minutes': 60, 'hours': 60*60, 'days': 60*60*24, 'weeks': 60*60*24*7, 'months': 60*60*24*28}

        for ds in params['data_sources']:
            price_data = models.Candle.objects.filter(datasource_symbol__datasource__name=ds,
                                                      time__gte=params['from_date'], time__lte=params['to_date'],
                                                      period=params['candle_period'])

            # convert to dataframe.
            df = pd.DataFrame(list(price_data.values('datasource_symbol__symbol__name', 'time')))

            # Aggregate data.
            if len(df.index) > 0:
                rules = {'minutes': 'T', 'hours': 'H', 'days': 'D', 'weeks': 'W', 'months': 'M'}
                agg_df = df.groupby([pd.Grouper(key='time', freq=rules[params['aggregation_period']]),
                                     'datasource_symbol__symbol__name']).size().reset_index(name='count')

                # Count needs to be a % of max, rather than actual for heatmap chart
                agg_df['count'] = agg_df['count'] / maxagg[params['aggregation_period']] * 100

                # We need to convert to a string format that apexcharts can read.
                ds_chart_data = []
                all_symbols = agg_df['datasource_symbol__symbol__name'].drop_duplicates()
                for symbol in all_symbols:
                    symbol_df = agg_df[agg_df['datasource_symbol__symbol__name'] == symbol]
                    symbol_plot_data = []
                    for index, row in symbol_df.iterrows():
                        jstime = int(time.mktime(row["time"].timetuple())) * 1000
                        chartplot = [jstime, row['count']]
                        symbol_plot_data.append(chartplot)

                    symbol_plots = {'name': symbol, 'data': symbol_plot_data}
                    ds_chart_data.append(symbol_plots)

                # Add the dataframes to the data
                chart_data[ds] = ds_chart_data

            return chart_data

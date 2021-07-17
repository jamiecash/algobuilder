import json
import logging
from collections import Counter
from datetime import timedelta
from typing import List, Dict

from bokeh.embed import json_item
from bokeh.io import output_file
from bokeh.models import (BasicTicker, ColorBar, ColumnDataSource,
                          LinearColorMapper, PrintfTickFormatter, BasicTickFormatter, )
from bokeh.plotting import figure
from bokeh.sampledata.unemployment1948 import data as d

import pandas as pd
from bokeh.transform import transform
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

    # Logger
    __log = logging.getLogger(__name__)

    def get(self, request):
        output_file("unemploymemt.html")

        d.Year = d.Year.astype(str)
        data = d.set_index('Year')
        data.drop('Annual', axis=1, inplace=True)
        data.columns.name = 'Month'

        # reshape to 1D array or rates with a month and year for each row.
        df = pd.DataFrame(data.stack(), columns=['rate']).reset_index()

        self.__log.info(df)

        source = ColumnDataSource(df)

        # this is the colormap from the original NYTimes plot
        colors = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
        mapper = LinearColorMapper(palette=colors, low=df.rate.min(), high=df.rate.max())

        p = figure(plot_width=800, plot_height=300, title="US unemployment 1948—2016",
                   x_range=list(data.index), y_range=list(reversed(data.columns)),
                   toolbar_location=None, tools="", x_axis_location="above")

        p.rect(x="Year", y="Month", width=1, height=1, source=source,
               line_color=None, fill_color=transform('rate', mapper))

        color_bar = ColorBar(color_mapper=mapper,
                             ticker=BasicTicker(desired_num_ticks=len(colors)),
                             formatter=PrintfTickFormatter(format="%d%%"))

        p.add_layout(color_bar, 'right')

        p.axis.axis_line_color = None
        p.axis.major_tick_line_color = None
        p.axis.major_label_text_font_size = "7px"
        p.axis.major_label_standoff = 0
        p.xaxis.major_label_orientation = 1.0

        jsontxt = json.dumps(json_item(p))

        return render(self.request, self.template_name, {'chart': jsontxt})

    def post(self, request):
        return HttpResponse("POST not supported", status=404)


class QualityView(View):
    """
    The data quality scatter plot

    The populated form will be retrieved from the request.POST and will contain the following values:

    """

    # Logger
    __log = logging.getLogger(__name__)

    form_class = PriceDataQualityForm
    template_name = 'pricedata/quality.html'

    def get(self, request):
        # Get chart data for initial values
        chart_data = QualityView.get_charts(self.initial)

        return render(self.request, self.template_name, {'form': self.form_class(initial=self.initial),
                                                         'charts': chart_data})

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Get chart data
            chart_data = QualityView.get_charts(form.cleaned_data)

            return render(self.request, self.template_name, {'form': self.form_class, 'charts': chart_data})
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
    def get_charts(params: Dict) -> Dict[str, List]:
        """
        Gets the charts
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

        :return: Dict[datasource_name: List(chart JSON text, footnote)].
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

                # Convert time to str
                agg_df['time'] = agg_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')

                # Generate heatmap chart. Colours range from green to red using range to max agg lookup for
                # aggregation_period
                source = ColumnDataSource(agg_df)
                QualityView.__log.debug(f"Producing JSON data for heatmap using source data: {source.data}")
                colors = ["#B21F35", "#D82735", "#FF7435", "#FFA135", "#FFCB35", "#FFF735", "#16DD36", "#009E47",
                          "#00753A"]
                mapper = LinearColorMapper(palette=colors, low=0, high=maxagg[params['aggregation_period']])

                p = figure(title=f"Prices available by time period and symbol for {ds}",
                           x_range=agg_df['time'].drop_duplicates(),
                           y_range=agg_df['datasource_symbol__symbol__name'].drop_duplicates(),
                           toolbar_location=None, tools="", x_axis_location="above")

                p.rect(x="time", y="datasource_symbol__symbol__name", width=1, height=1, source=source, line_color=None,
                       fill_color=transform('count', mapper))

                color_bar = ColorBar(color_mapper=mapper,
                                     ticker=BasicTicker(desired_num_ticks=len(colors)),
                                     formatter=BasicTickFormatter())

                p.add_layout(color_bar, 'right')

                p.axis.axis_line_color = None
                p.axis.major_tick_line_color = None
                p.axis.major_label_text_font_size = "7px"
                p.axis.major_label_standoff = 0
                p.xaxis.major_label_orientation = 1.0

                jsontxt = json.dumps(json_item(p))

                QualityView.__log.debug(f"Produced JSON text for graph: {jsontxt}")

                # Add the json text and rowcount to the pre aggregated data
                footnote = f"{len(df.index):,} price candles represented. {len(agg_df.index):,} aggregated rows " \
                           f"plotted."
                chart_data[ds] = [jsontxt, footnote]

            return chart_data

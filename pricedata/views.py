import json
import logging
from collections import Counter
from datetime import timedelta
from typing import Dict

from bokeh.embed import json_item
from bokeh.models import (BasicTicker, ColorBar, ColumnDataSource,
                          LinearColorMapper, BasicTickFormatter, BoxSelectTool, CustomJS, HoverTool,
                          DatetimeTickFormatter, CDSView, BooleanFilter, )
from bokeh.plotting import figure
from bokeh.transform import transform

import pandas as pd
from django.contrib import messages
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from algobuilder.utils import django_cache
from pricedata import models, forms
from pricedata.forms import TestForm
from .tasks import test_task


class IndexView(View):
    form_class = None
    template_name = "pricedata/index.html"

    def get(self, request):
        return render(self.request, self.template_name, {})

    def post(self, request):
        return HttpResponse("POST not supported", status=404)


class TestView(View):
    form_class = TestForm
    template_name = "pricedata/test.html"

    # Logger
    __log = logging.getLogger(__name__)

    def form_valid(self, form):
        x = form.cleaned_data.get('x')
        y = form.cleaned_data.get('x')
        test_task.delay(x, y)
        messages.success(self.request, 'We are doing the maths. Wait a moment and refresh this page.')
        return render(self.request, self.template_name, {'test_text': 'Test View'})

    def get(self, request):
        return render(self.request, self.template_name, {'form': self.form_class()})

    def post(self, request):
        form = self.form_class(request.POST)
        if form.is_valid():
            x = form.cleaned_data.get('x')
            y = form.cleaned_data.get('y')
            test_task.delay(x, y)
            messages.success(self.request, 'We are doing the maths. Wait a moment and refresh this page.')
            return render(self.request, self.template_name, {'form': self.form_class(),
                                                             'messages': messages})


class MetricsView(View):
    """
    Data metrics
    """

    # Logger
    __log = logging.getLogger(__name__)

    form_class = forms.PriceDataMetricsForm
    template_name = 'pricedata/metrics.html'

    def get(self, request):
        # Initial params for chart
        initial_params = {'data_source': 'all', 'candle_period': ViewData.get_most_used_period()}

        # Get summary data
        data = ViewData().retrieve_price_data(initial_params['candle_period'])
        summarised_data = ViewData().summarise_data(data)
        formatted_data = MetricsView.__format_data(summarised_data=summarised_data,
                                                   datasource_name=initial_params['data_source'])

        return render(self.request, self.template_name,
                      {'form': self.form_class(initial=initial_params),
                       'summary_data': formatted_data,
                       'datasource': initial_params['data_source']})

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Cleaned data
            form_data = form.cleaned_data

            # Get summary data
            data = ViewData().retrieve_price_data(form_data['candle_period'])
            summarised_data = ViewData().summarise_data(data)
            formatted_data = MetricsView.__format_data(summarised_data=summarised_data,
                                                       datasource_name=form_data['data_source'])

            return render(self.request, self.template_name,
                          {'form': self.form_class(initial=form_data),
                           'summary_data': formatted_data,
                           'datasource': form_data['data_source']})

        else:
            return HttpResponse("Invalid form", status=404)

    @staticmethod
    def __format_data(summarised_data: pd.DataFrame, datasource_name: str = 'all') -> str:
        """
        Returns the HTML for the provided summary data. Formats as required for display.

        :param summarised_data: A dataframe containing the summary data
        :param datasource_name: The name of the datasource to produce the summary data for. 'all' will produce the
            summarised data across all datasources.

        :return: html as string
        """

        display = summarised_data

        # Merge the agg functions for datasource into cells for each aggregation period
        for agg in ['minutes', 'hours', 'days', 'weeks', 'months']:
            # Get the min, max and avg columns and consolidate into a new column. Drop the existing ones.
            min_col = f'{agg}_min_{datasource_name}'
            max_col = f'{agg}_max_{datasource_name}'
            avg_col = f'{agg}_avg_{datasource_name}'
            display[agg] = 'min:' + display[min_col].astype(str) + ' max:' + display[max_col].astype(
                str) + ' avg:' + display[avg_col].astype(str)

        # Rename the columns that we will be keeping
        display = display.rename(
            columns={'symbol': 'Symbol', 'instrument_type': 'Instrument Type',
                     f'first_{datasource_name}': 'First Price',
                     f'last_{datasource_name}': 'Last Price', 'minutes': 'Minutes', 'hours': 'Hours', 'days': 'Days',
                     'weeks': 'Weeks',
                     'months': 'Months'})

        # Reorder the columns, excluding any that we dont want to keep
        display = display[
            ['Symbol', 'Instrument Type', 'First Price', 'Last Price', 'Minutes', 'Hours', 'Days', 'Weeks',
             'Months']]

        # Convert to HTML. Then set style for thead. We wont set the table style through the to_html method as this will
        # keep the default dataframe style.
        html = display.to_html(index=False)
        html = html.replace("<thead>", '<thead class="table-dark">')
        html = html.replace('class="dataframe"', 'class="table table-striped"')

        return html


class QualityView(View):
    """
    The data quality scatter plot
    """

    # Logger
    __log = logging.getLogger(__name__)

    form_class = forms.PriceDataQualityForm
    template_name = 'pricedata/quality.html'

    def get(self, request):
        # Get summary data
        data = ViewData().retrieve_price_data(ViewData.get_most_used_period())
        summarised_data = ViewData().summarise_data(data)

        # Initial params for chart
        initial_params = QualityView.__get_initial_form_values(summarised_data)

        # Get the charts
        charts = self.__create_charts(data, summarised_data, initial_params)

        return render(self.request, self.template_name,
                      {'form': self.form_class(initial=initial_params),
                       'charts': charts})

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Cleaned data
            form_data = form.cleaned_data

            # Get summary data
            data = ViewData.retrieve_price_data(form_data['candle_period'])
            summarised_data = ViewData.summarise_data(data)

            # Get the best aggregation period for the new from and to dates
            form_data['aggregation_period'] = \
                QualityView.__get_best_aggregation_period(form_data['from_date'], form_data['to_date'], 100)

            # Get the charts
            charts = self.__create_charts(data, summarised_data, form_data)

            return render(self.request, self.template_name,
                          {'form': self.form_class(initial=form_data),
                           'charts': charts})

        else:
            return HttpResponse("Invalid form", status=404)

    @staticmethod
    def __get_initial_form_values(summarised_data: pd.DataFrame) -> Dict:
        """
        Gets the initial values for the form from the summarised data
        :return: Dict of initial values
        """

        # From and to date will be the min first and max last dates in the summarised data for all datasources.
        # Datasources will be all. Period will have already been used to create the summary data, but will be set again.
        initial = {'from_date': summarised_data['first_all'].min(), 'to_date': summarised_data['last_all'].max(),
                   'data_sources': [ds.name for ds in models.DataSource.objects.all()],
                   'candle_period': ViewData.get_most_used_period()}

        # Aggregation period will be the best aggregation period to end up with ~100 plots
        initial['aggregation_period'] = \
            QualityView.__get_best_aggregation_period(initial['from_date'], initial['to_date'], 100)

        return initial

    @staticmethod
    def __get_best_aggregation_period(from_date, to_date, target_plots):
        """
        Gets the best aggregation period to use to display ~target_plots plots between the supplied dates
        :param from_date:
        :param to_date:
        :param target_plots: The target number of plots to use for calculating the best aggregation period
        :return: aggregation period
        """

        duration = to_date - from_date

        candles_per_aggregation_period_for_timeframe = {
            'months': duration.days / 30,
            'weeks': duration.days / 7,
            'days': duration.days,
            'hours': duration.days * 24,
            'minutes': duration.days * 24 * 60}

        # Start at months, then keep trying more granular periods until we find one that is over target. When we find
        # first one over target, use prior one.
        last_agg = 'months'
        aggregation_period = None
        i = 0
        while aggregation_period is None:
            agg = list(candles_per_aggregation_period_for_timeframe.keys())[i]
            # get the max number of candles for all data sources for this aggregation period
            if candles_per_aggregation_period_for_timeframe[agg] > target_plots:
                aggregation_period = last_agg  # Done, save the last aggregation period that was not over our threshold
            else:
                last_agg = agg

                # If we are on the last one, set to 'minutes', otherwise try the next one.
                if i == len(candles_per_aggregation_period_for_timeframe.keys()) - 1:
                    aggregation_period = 'minutes'
                else:
                    i += 1

        return aggregation_period

    @staticmethod
    def __create_charts(price_data: pd.DataFrame, summary_data: pd.DataFrame, params: Dict) -> Dict[str, str]:
        """
        Creates the heatmap charts for the supplied price data. One chart per
        :param price_data: The price data to use to create the chart
        :param summary_data: The summarised price data to use to determine ranges for heatmap
        :param params: Dict containing:
            from_date: The from date for the chart.
            to_date: The from date for the chart.
            data_sources: List of datasource names to include.
            candle_period: The candle period to assess.
            aggregation_period: 'minutes', 'hours', 'days', 'weeks', or 'months'. Will aggregate plots to period and
                colour for count of values. This cannot be less than the candle period that the price data was
                retrieved for, i.e., if price data is daily candles [1D], then period must be 'days', 'weeks' or
                'months'. It cannot be 'minutes' or 'hours'. Colouring will use the summary data to determine max ranges
                for aggregation period.

        :return: Dict[datasource_name: chart JSON HTML].
        """
        chart_htmls = {}

        for ds in params['data_sources']:
            # filter the price data
            chart_data = price_data[(price_data['time'] >= params['from_date']) &
                                    (price_data['time'] <= params['to_date']) &
                                    (price_data['datasource'].isin(params['data_sources']))]

            # Get the maximum number of prices for the aggregation period for use in heatmap range.
            max_agg = summary_data[f"{params['aggregation_period']}_max_all"].max()

            # Aggregate data for the aggregation period.
            if len(chart_data.index) > 0:
                rules = {'minutes': 'T', 'hours': 'H', 'days': 'D', 'weeks': 'W', 'months': 'M'}
                aggregated_data = chart_data.groupby([pd.Grouper(key='time', freq=rules[params['aggregation_period']]),
                                                     'symbol']).size().reset_index(name='count')

                # Convert time to str
                aggregated_data['time'] = aggregated_data['time'].dt.strftime('%Y-%m-%d %H:%M:%S')

                # Generate heatmap chart. Colours range from green to red using range 0 to max_agg
                source = ColumnDataSource(aggregated_data)
                QualityView.__log.debug(f"Producing JSON data for heatmap using source data: {source.data}")
                colors = ["#B21F35", "#D82735", "#FF7435", "#FFA135", "#FFCB35", "#FFF735", "#16DD36", "#009E47",
                          "#00753A"]
                mapper = LinearColorMapper(palette=colors, low=0, high=max_agg)

                # Select tool to drill down into more granular period, and hover tool to show time, symbol and count on
                # mouseover
                select = BoxSelectTool(dimensions='width',
                                       description='Select chart area to drill down into more granular time periods.')

                hover = HoverTool()

                # Display date and symbol for hover
                tooltips = [
                    ("Symbol / Time", "@symbol, @time"),
                    ("Num Candles", "@count"),
                ]

                p = figure(title=f"Prices available by time period and symbol for {ds}",
                           plot_width=1000, x_range=aggregated_data['time'].drop_duplicates(),
                           y_range=aggregated_data['symbol'].drop_duplicates(),
                           toolbar_location='below', tools=[hover, select], tooltips=tooltips,
                           x_axis_location="above")

                p.rect(x="time", y="symbol", width=1, height=1, source=source, line_color=None,
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

                # When a range is selected on the chart, the form from and to dates should be updated. Selection
                # contains every element selected across both x and y axis. We will get the from and 2 dates using the
                # first and last item in the selection. We will then populate the from date and to date form objects by
                # searching for their ids, which should be id_from_date and id_to_date.
                source.selected.js_on_change(
                    "indices",
                    CustomJS(
                        args=dict(source=source),
                        code="""
                        var inds = cb_obj.indices;
                        var data = source.data;
                        var xstart = data['time'][inds[0]]
                        
                        // Try getting +1
                        var xend = data['time'][inds[inds.length - 1] +1 ]

                        // If undefined, get last
                        if (typeof(xend) == "undefined") {
                            xend = data['time'][inds[inds.length - 1]]
                        }         
                        
                        //Update the field forms
                        const from_date_element = document.getElementById("id_from_date");
                        const to_date_element = document.getElementById("id_to_date");
                        from_date_element.value = xstart
                        to_date_element.value = xend
                        """,
                    ),
                )

                json_txt = json.dumps(json_item(p))

                QualityView.__log.debug(f"Produced JSON text for {ds} graph: {json_txt}")

                # Add the json html
                chart_htmls[ds] = json_txt

            return chart_htmls


class CandlesView(View):
    """
    OHLC Candle chart
    """

    # Logger
    __log = logging.getLogger(__name__)

    form_class = forms.PriceDataCandleForm
    template_name = 'pricedata/candles.html'

    def get(self, request):
        # Initial params for chart. 1st datasource and period. No dates or symbol.
        to_date = timezone.now()
        from_date = to_date - timedelta(hours=1)

        # Initial params. Datasource candle period is set on form as first item in list. This saves retrieving the data
        # here again.
        initial_params = {'from_date': from_date, 'to_date': to_date}

        return render(self.request, self.template_name,
                      {'form': self.form_class(initial=initial_params)})

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Cleaned data
            form_data = form.cleaned_data

            # Get the data source candle period so that we can use the data source and period to get the right candle
            dscp_id = form_data['datasource_period']
            dscp = models.DataSourceCandlePeriod.objects.get(pk=dscp_id)

            # Get candle data
            candles = models.Candle.objects.filter(datasource_symbol__datasource=dscp.datasource,
                                                   period=dscp.period,
                                                   time__gte=form_data['from_date'],
                                                   time__lte=form_data['to_date'],
                                                   datasource_symbol__symbol__name=form_data['symbol']
                                                   )

            candle_data = pd.DataFrame(list(candles.values('datasource_symbol__symbol__name', 'time', 'bid_open',
                                                           'bid_high', 'bid_low', 'bid_close', 'ask_open', 'ask_high',
                                                           'ask_low', 'ask_close', 'volume')))

            # Get the chart
            chart = self.__create_chart(candle_data)

            return render(self.request, self.template_name,
                          {'form': self.form_class(initial=form_data),
                           'symbol': form_data['symbol'],
                           'chart': chart})

        else:
            return HttpResponse("Invalid form", status=404)

    @staticmethod
    def __create_chart(candle_data: pd.DataFrame, bid_or_ask: str = 'ask') -> str:
        """
        Creates the OHLC price data candle chart from the supplied candle data
        :param candle_data: The candle data containing the OHLC data for the chart
        :param bid_or_ask: Whether to use bid or ask prices. Default is ask

        :return: chart JSON HTML.
        """
        chart_html = {}

        # Convert time to str
        # candle_data['time'] = candle_data['time'].dt.strftime('%Y-%m-%d %H:%M:%S')

        # Only create chart if we have some data
        if candle_data is not None and len(candle_data.index) > 0:
            # Get the symbol for the first cell
            symbol = candle_data['datasource_symbol__symbol__name'][0]

            # We will make it easy for ourselves later by adding OHLC columns using the existing bid or ask OHLC columns
            # depending on bid_or_ask param
            candle_data['open'] = candle_data[f'{bid_or_ask}_open']
            candle_data['high'] = candle_data[f'{bid_or_ask}_high']
            candle_data['low'] = candle_data[f'{bid_or_ask}_low']
            candle_data['close'] = candle_data[f'{bid_or_ask}_close']

            # Generate candle chart.
            source = ColumnDataSource(candle_data)
            CandlesView.__log.debug(f"Producing JSON data for candle chart for symbol {symbol} using source data: "
                                    f"{source.data}")

            # Date formatter. Used on axis
            dtfmt = DatetimeTickFormatter(days='%Y-%m-%d', hours='%Y-%m-%d %H:%M', hourmin='%Y-%m-%d %H:%M',
                                          minutes='%Y-%m-%d %H:%M:%S', seconds='%Y-%m-%d %H:%M:%S')

            # Display date and OHLCV values for hover
            hover = HoverTool(
                tooltips=[
                    ("Time", "@time{'%Y-%m-%d %H:%M:%S'}"),
                    ("Open", "@open"),
                    ("High", "@high"),
                    ("Low", "@low"),
                    ("Close", "@close"),
                    ("Volume", "@volume"),
                ],

                formatters={
                    '@time': 'datetime'
                },
                mode='mouse'
            )

            p = figure(plot_width=1000, x_axis_type="datetime", toolbar_location='below', tools=[hover],
                       x_axis_location="above", )

            # Format date
            p.xaxis[0].formatter = dtfmt

            # Candle wick, high to low
            p.segment(source=source, x0='time', y0='high', x1='time', y1='low', color="black")

            # Width will be the number of milliseconds between the times - 10% for spacing
            width = (candle_data['time'][1] - candle_data['time'][0]).total_seconds() * 1000 * .9

            # Candle colour will depend on whether it has increased or decreased between open and close
            inc = CDSView(source=source, filters=[BooleanFilter(source.data['close'] > source.data['open'])])
            dec = CDSView(source=source, filters=[BooleanFilter(source.data['open'] > source.data['close'])])

            p.vbar(source=source, view=inc, x='time', top='open', bottom='close', width=width, fill_color="#D5E1DD",
                   line_color="black")
            p.vbar(source=source, view=dec, x='time', top='open', bottom='close', width=width, fill_color="#F2583E",
                   line_color="black")

            p.axis.axis_line_color = None
            p.axis.major_tick_line_color = None
            p.axis.major_label_text_font_size = "7px"
            p.axis.major_label_standoff = 0
            p.xaxis.major_label_orientation = 1.0
            p.grid.grid_line_alpha = 0.3

            json_txt = json.dumps(json_item(p))

            CandlesView.__log.debug(f"Produced JSON text for {symbol} graph: {json_txt}")

            # Add the json html
            chart_html = json_txt

        return chart_html


class ViewData:
    """
    A class to retrieve and summarise the data required in the price data views
    """

    @django_cache(cache_name='price_data')
    def retrieve_price_data(self, period: str) -> pd.DataFrame:
        """
        Retrieves the price data.

        :param period: The candle period that we are producing the dashboard for

        :return: DataFrame containing price data
        """
        sql = """SELECT	s.name AS symbol,
                        s.instrument_type AS instrument_type,
                        ds.name AS datasource,
                        cdl.time AS time
                FROM public.pricedata_datasourcesymbol dss
                    INNER JOIN pricedata_datasource ds ON dss.datasource_id = ds.id
                    INNER JOIN pricedata_symbol s ON dss.symbol_id = s.id
                    INNER JOIN pricedata_candle cdl ON cdl.datasource_symbol_id = dss.id  
                WHERE dss.retrieve_price_data = true
                    AND cdl.period = %(period)s"""

        price_data = pd.read_sql_query(sql=sql, con=connection, params={'period': period})

        return price_data

    @django_cache(cache_name='price_data')
    def summarise_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Produces a data summary dashboard from provided data showing:
            * The datetime of the first and last candles for each datasource;
            * The number of candles for each datasource;
            * The minimum, maximum and average number of candles for each aggregation period for each datasource; and
            * The minimum, maximum and average number of candles for each aggregation period across all datasources.

        :param price_data: The candle period that we are producing the dashboard for
        """
        # First group by to get min and max times
        grouped = price_data.groupby(['symbol', 'instrument_type', 'datasource']).agg(first=('time', 'min'),
                                                                                      last=('time', 'max'),
                                                                                      count=('time', 'count'))

        # Now get min, max and mean for each aggregation period for each datasource.
        # 'minutes': 'T', 'hours': 'H', 'days': 'D', 'weeks': 'W', 'months': 'M'
        aggs = {'minutes': 'T', 'hours': 'H', 'days': 'D', 'weeks': 'W', 'months': 'M'}

        for key in aggs:
            # Get counts for aggregation period, then group by symbol, instrument type and datasource to get min,
            # max and avg counts for aggregation period
            agg_period_ungrouped = price_data.groupby(
                ['symbol', 'instrument_type', 'datasource', pd.Grouper(key='time', freq=aggs[key])]).agg(
                count=('time', 'count'))
            agg_period_grouped = agg_period_ungrouped.groupby(['symbol', 'instrument_type', 'datasource']).agg(
                min=('count', 'min'), max=('count', 'max'), avg=('count', 'median'))

            # Rename columns to include aggregation period key, then merge into original dataframe
            agg_period_grouped = agg_period_grouped.rename(
                columns={'min': f'{key}_min', 'max': f'{key}_max', 'avg': f'{key}_avg'})
            grouped = grouped.join(agg_period_grouped, on=['symbol', 'instrument_type', 'datasource'])

        # Now unstack, so we show columns for each datasource
        grouped = grouped.unstack()

        # Create the same aggregations but across all datasources
        agg_cols = set([x[0] for x in grouped.columns])
        ds_cols = set([x[1] for x in grouped.columns])

        for agg_col in agg_cols:
            if '_min' in agg_col or agg_col == 'first':
                grouped[(agg_col, 'all')] = grouped[[(agg_col, ds) for ds in ds_cols]].min(axis=1)
            elif '_max' in agg_col or agg_col == 'last':
                grouped[(agg_col, 'all')] = grouped[[(agg_col, ds) for ds in ds_cols]].max(axis=1)
            elif '_avg' in agg_col:
                grouped[(agg_col, 'all')] = grouped[[(agg_col, ds) for ds in ds_cols]].mean(axis=1)

        # Flatten the columns and reset the index
        grouped.columns = ['_'.join(col).strip() for col in grouped.columns]
        grouped = grouped.reset_index()

        return grouped

    @staticmethod
    def get_most_used_period() -> str:
        """
        Returns the most used candle period. This will be the period that is common across the largest
        number of datasources. This will be used as the initial value for the forms
        :return: period
        """
        datasources = [ds.name for ds in models.DataSource.objects.all()]
        periods = [dscp.period for dscp in
                   models.DataSourceCandlePeriod.objects.filter(datasource__name__in=datasources)]
        most_used_period = None if len(periods) == 0 else Counter(periods).most_common(1)[0][0]

        return most_used_period

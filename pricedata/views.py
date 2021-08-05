import json
import logging
from collections import Counter
from datetime import timedelta
from typing import Dict, List

from bokeh.embed import json_item
from bokeh.layouts import gridplot
from bokeh.models import (BasicTicker, ColorBar, ColumnDataSource,
                          LinearColorMapper, BasicTickFormatter, BoxSelectTool, CustomJS, HoverTool,
                          DatetimeTickFormatter, CDSView, BooleanFilter, )
from bokeh.plotting import figure
from bokeh.transform import transform

import pandas as pd
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View

from pricedata import models, forms, tasks


class IndexView(View):
    form_class = None
    template_name = "pricedata/index.html"

    def get(self, request):
        # Return with the batch params
        return render(self.request, self.template_name, BatchManager().get_batch_params())

    def post(self, request):
        # Run the batch
        tasks.create_summary_data.delay()

        # Redirect to index page. Index will pick up and report batch status
        return redirect('/pricedata')


class MetricsView(View):
    """
    Data metrics
    """

    # Logger
    __log = logging.getLogger(__name__)

    form_class = forms.PriceDataMetricsForm
    template_name = 'pricedata/metrics.html'

    def get(self, request):
        # Initial params for chart and create params for post
        initial_params = {'datasource': 'all', 'candle_period': get_most_used_period()}
        params = {'form': self.form_class(initial=initial_params), 'datasource': initial_params['datasource']}
        params = BatchManager().get_batch_params(params)

        # Redirect to index if we dont have a batch available
        if not BatchManager().available:
            return redirect('/pricedata')
        else:
            # Get the summary data
            data = BatchManager.get_summary_data(initial_params['candle_period'], initial_params['datasource'])

            # Format the data and add to params
            formatted_data = MetricsView.__format_data(data=data)
            params['summary_data'] = formatted_data

            return render(self.request, self.template_name, params)

    def post(self, request):
        # Get form from POST and check whether it's valid:
        form = self.form_class(request.POST)
        if form.is_valid():
            # Cleaned data
            form_data = form.cleaned_data

            # Params
            params = {'form': self.form_class(initial=form_data), 'datasource': form_data['datasource']}
            params = BatchManager().get_batch_params(params)

            # Redirect to index if we dont have a batch available
            if not BatchManager().available:
                return redirect('/pricedata', params)
            else:
                # Get the summary data
                data = BatchManager.get_summary_data(form_data['candle_period'], form_data['datasource'])

                # Format the data and add to params
                formatted_data = MetricsView.__format_data(data=data)
                params['summary_data'] = formatted_data

                return render(self.request, self.template_name, params)
        else:
            return HttpResponse("Invalid form", status=404)

    @staticmethod
    def __format_data(data: pd.DataFrame) -> str:
        """
        Returns the HTML for the provided summary data. Formats as required for display.

        :param data: A dataframe containing the summary data

        :return: html as string
        """

        display = data

        # Merge the agg functions for datasource into cells for each aggregation period
        for agg in ['minutes', 'hours', 'days', 'weeks', 'months']:
            # Get the min, max and avg columns and consolidate into a new column.
            min_col = f'{agg}_min'
            max_col = f'{agg}_max'
            avg_col = f'{agg}_avg'

            # Column name will be the agg but with a capital first letter for display purposes
            display[agg.capitalize()] = 'min:' + display[min_col].astype(str) + ' max:' + display[max_col].astype(
                str) + ' avg:' + display[avg_col].astype(str)

        # Rename first and last price columns. The rest should already be ok
        display = display.rename(
            columns={'first_candle_time': 'First Price', 'last_candle_time': 'Last Price'})

        # Select the columns that we want to keep in the correct order
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
        # Redirect to index if we don't have a batch available
        if not BatchManager().available:
            return redirect('/pricedata')
        else:
            # Get the summary data
            sumdata = BatchManager.get_summary_data(get_most_used_period(), 'all')

            # Get initial values from summary data
            initial_params = QualityView.__get_initial_form_values(sumdata)

            # Get the aggregate data and chart for all datasources
            all_charts = []
            for datasource in initial_params['datasources']:
                aggdata = BatchManager.get_aggregate_data(initial_params['candle_period'], datasource,
                                                          initial_params['aggregation_period'],
                                                          initial_params['from_date'], initial_params['to_date'])

                # Create chart and append to charts as tuple with datasource
                chart = self.__create_chart(aggdata, sumdata, initial_params['aggregation_period'], datasource)
                all_charts.append((datasource, chart))

            # Add from and charts to params
            params = {'form': self.form_class(initial=initial_params), 'charts': all_charts}
            params = BatchManager().get_batch_params(params)

            return render(self.request, self.template_name, params)

    def post(self, request):
        # Redirect to index if we dont have a batch available
        if not BatchManager().available:
            return redirect('/pricedata')
        else:
            # Get form from POST and check whether it's valid:
            form = self.form_class(request.POST)
            if form.is_valid():
                # Cleaned data
                form_data = form.cleaned_data

                # Get the summary data
                sumdata = BatchManager.get_summary_data(get_most_used_period(), 'all')

                # Get the best aggregation period for the date range
                aggregation_period = \
                    QualityView.__get_best_aggregation_period(form_data['from_date'], form_data['to_date'],
                                                              settings.ALGOBUILDER_PRICEDATA_MAXPLOTS)
                form_data['aggregation_period'] = aggregation_period

                # Get the aggregate data and chart for all datasources
                all_charts = []
                for datasource in form_data['datasources']:
                    aggdata = BatchManager.get_aggregate_data(form_data['candle_period'], datasource,
                                                              aggregation_period, form_data['from_date'],
                                                              form_data['to_date'])

                    # Create chart and append to charts as tuple with datasource
                    chart = self.__create_chart(aggdata, sumdata, aggregation_period, datasource)
                    all_charts.append((datasource, chart))

                # Add from and charts to params
                params = {'form': self.form_class(initial=form_data), 'charts': all_charts}
                params = BatchManager().get_batch_params(params)

                return render(self.request, self.template_name, params)

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
        initial = {'from_date': summarised_data['first_candle_time'].min(),
                   'to_date': summarised_data['last_candle_time'].max(),
                   'datasources': [ds.name for ds in models.DataSource.objects.all()],
                   'candle_period': get_most_used_period()}

        # Aggregation period will be the best aggregation period to end up with ~100 plots
        initial['aggregation_period'] = \
            QualityView.__get_best_aggregation_period(initial['from_date'], initial['to_date'],
                                                      settings.ALGOBUILDER_PRICEDATA_MAXPLOTS)

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
    def __create_chart(aggregate_data: pd.DataFrame, summary_data: pd.DataFrame, aggregation_period: str,
                       datasource: str) -> str:
        """
        Creates the heatmap chart for the supplied aggregate_data.
        :param aggregate_data: The price data to use to create the chart
        :param summary_data: The summarised price data to use to determine ranges for heatmap
        :param aggregation_period: minutes', 'hours', 'days', 'weeks', or 'months'. Will aggregate plots to period and
                colour for count of values. This cannot be less than the candle period that the price data was
                retrieved for, i.e., if price data is daily candles [1D], then period must be 'days', 'weeks' or
                'months'. It cannot be 'minutes' or 'hours'. Colouring will use the summary data to determine max ranges
                for aggregation period.
        :param datasource: The datasource name

        :return: JSON HTML.
        """
        # Get the maximum number of prices for the aggregation period for use in heatmap range.
        max_agg = summary_data[f"{aggregation_period}_max"].max()

        # Aggregate data for the aggregation period.
        if len(aggregate_data.index) > 0:
            # Convert time to str
            aggregate_data['time'] = aggregate_data['time'].dt.strftime('%Y-%m-%d %H:%M:%S')

            # Generate heatmap chart. Colours range from green to red using range 0 to max_agg
            source = ColumnDataSource(aggregate_data)
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
                ("Num Candles", "@num_candles"),
            ]

            p = figure(title=f"Prices available by time period and symbol for {datasource}",
                       plot_width=1000, x_range=aggregate_data['time'].drop_duplicates(),
                       y_range=aggregate_data['symbol'].drop_duplicates(),
                       toolbar_location='below', tools=[hover, select], tooltips=tooltips,
                       x_axis_location="above")

            p.rect(x="time", y="symbol", width=1, height=1, source=source, line_color=None,
                   fill_color=transform('num_candles', mapper))

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

            QualityView.__log.debug(f"Produced JSON text for {datasource} graph: {json_txt}")

            # Return json html
            return json_txt


class CandlesView(View):
    """
    OHLC Candle / bar chart
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
            bid_ask = form_data['bid_ask']
            chart_type = form_data['chart_type']
            chart = self.__create_chart(candle_data, bid_or_ask=bid_ask, chart_type=chart_type)

            return render(self.request, self.template_name,
                          {'form': self.form_class(initial=form_data),
                           'symbol': form_data['symbol'],
                           'chart': chart})

        else:
            return HttpResponse("Invalid form", status=404)

    @staticmethod
    def __create_chart(candle_data: pd.DataFrame, bid_or_ask: str = 'ask', chart_type: str = 'candle') -> str:
        """
        Creates the OHLC price data candle or bar chart and volume vbar chart from the supplied candle data
        :param candle_data: The candle data containing the OHLC data for the chart
        :param bid_or_ask: Whether to use bid or ask prices. Default is ask
        :param chart_type: candle or bar. Whether to produce a OHLC candle or bar chart

        :return: HTML for gri d of 2 charts. One for the candle or bar chart and one for the volume chart
        """

        # Logger
        log = logging.getLogger(__name__)

        chart_html = ""

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

            # We will have a grid of 2 plots sharing the same source
            plots = []
            source = ColumnDataSource(candle_data)
            CandlesView.__log.debug(f"Producing JSON data for {chart_type} chart for symbol {symbol} using source "
                                    f"data: {source.data}")

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

            # First figure is the candle or bar chart, 2nd is for the volume bar chart. Dates will be plotted above
            # first. Toolbar will be below second.
            p1 = figure(plot_width=1000, x_axis_type="datetime", tools=[hover], x_axis_location="above")
            p2 = figure(plot_width=1000, x_axis_type="datetime", tools=[hover], plot_height=round(p1.plot_height / 3),
                        x_range=p1.x_range)
            p2.axis[0].visible = False
            plots = [p1, p2]

            # Candle (for candle chart) or wick (for bar chart) colour will depend on whether it has increased or
            # decreased between open and close
            inc = CDSView(source=source, filters=[BooleanFilter(source.data['close'] > source.data['open'])])
            dec = CDSView(source=source, filters=[BooleanFilter(source.data['open'] > source.data['close'])])
            views = {inc: '#555555', dec: '#F2583E'}  # Colours for inc and dec views

            # Draw candle with wick, or line with high and low markers depending on whether we are drawing candles or
            # bars.
            width = 0  # This will be calculated depending on chart type
            if chart_type == 'candle':
                # Candle body width will be the number of milliseconds between the times - 20% for
                # spacing.
                width = (candle_data['time'][1] - candle_data['time'][0]).total_seconds() * 1000 * .8

                # Candle wick
                plots[0].segment(source=source, x0='time', y0='high', x1='time', y1='low', color="black")

                # The candle body. Colour will depend on open / close prices and will use inc and dec views declared
                # above.
                for view in views:
                    plots[0].vbar(source=source, view=view, x='time', top='open', bottom='close', width=width,
                                  fill_color=views[view], line_color="black")

            elif chart_type == 'bar':
                # Open / close tick length will be the number of milliseconds between the times - 70% for spacing.
                width = (candle_data['time'][1] - candle_data['time'][0]).total_seconds() * 1000 * .3

                # Bar. Colour will depend on whether this opened higher than closed (red) or closed higher than opened
                # (black). They will use inc / dec views declared earlier.
                for view in views:
                    # The main bar
                    plots[0].segment(source=source, view=view, x0='time', y0='high', x1='time', y1='low',
                                     color=views[view])

                    # Open line on left and close on right
                    plots[0].ray(source=source, view=view, x='time', y='open', length=width, angle=180,
                                 color=views[view], angle_units="deg")
                    plots[0].ray(source=source, view=view, x='time', y='close', length=width, angle=0,
                                 color=views[view], angle_units="deg")
            else:
                log.warning(f"Invalid chart type of {chart_type} requested.")

            # Show volume as bars. We will use the width calculated for the candle or bar charts above to align.
            # Height should be a 1/3 of the height of the main plot.
            plots[1].vbar(source=source, x='time', top='volume', width=width)

            # Axis format for both plots
            for p in plots:
                # Format plot
                p.axis.axis_line_color = None
                p.axis.major_tick_line_color = None
                p.axis.major_label_text_font_size = "7px"
                p.axis.major_label_standoff = 0
                p.xaxis.major_label_orientation = 1.0
                p.grid.grid_line_alpha = 0.3

                p.xaxis[0].formatter = dtfmt

            # Create the grid and HTML
            grid = gridplot(plots, ncols=1, toolbar_location='below', toolbar_options=dict(logo=None))
            json_txt = json.dumps(json_item(grid))
            chart_html = json_txt

            CandlesView.__log.debug(f"Produced HTML for {symbol} graph: {chart_html}")

        return chart_html


class BatchManager:
    """
    Utility for using data summary batches
    """
    @property
    def available(self):
        """
        Whether there is a completed batch available
        :return:
        """
        # Get all completed batches
        batches = models.SummaryBatch.objects.filter(status=models.SummaryBatch.STATUS_COMPLETE).order_by('time')

        # Do we have any
        return batches is not None and len(batches) > 0

    @property
    def in_progress(self):
        """
        Whether a batch is in progress
        :return:
        """
        # TODO. This will show failed batches as in progress. Need to check celery queue.
        # Get all in progress batches
        batches = models.SummaryBatch.objects.filter(status=models.SummaryBatch.STATUS_IN_PROGRESS).order_by('time')

        # Do we have any
        return batches is not None and len(batches) > 0

    @property
    def last_available(self) -> models.SummaryBatch:
        """
        Returns the last available batch
        :return: Last batch. None if there aren't any.
        """
        # Get all completed batches
        batches = models.SummaryBatch.objects.filter(status=models.SummaryBatch.STATUS_COMPLETE).order_by('-time')

        # Do we have any
        return None if len(batches) == 0 else batches[0]

    def get_batch_params(self, params: Dict[str, any] = None) -> Dict[str, any]:
        """
        Populate params with the last_batch_time and batch_status.
        :param params: Params to add to. If not supplied, then new params will be created
        :return:
        """
        params = {} if params is None else params
        params['batch_available'] = self.available
        params['batch_in_progress'] = self.in_progress
        if self.last_available is not None:
            params['last_available_batch'] = self.last_available

        return params

    @staticmethod
    def get_summary_data(period: str, datasource: str = 'all') -> pd.DataFrame:
        """
        Gets the summary data from the last batch for the specified period
        :param period: The candle period for the summary data
        :param datasource: The datasource for the candle data. 'all' for a summary across all datasources. 'all' is
            default.
        :return:
        """
        # Get the last available batch
        last_batch = BatchManager().last_available

        if datasource == 'all':
            # Get the summary metrics for all datasources
            metrics = models.SummaryMetricAllDatasources.objects.filter(summary_batch=last_batch, period=period)
        else:
            # Get the datasource candle period fo the selected datasource and period
            dscp = models.DataSourceCandlePeriod.objects.filter(datasource__name=datasource, period=period)[0]
            metrics = models.SummaryMetric.objects.filter(summary_batch=last_batch, datasource_candleperiod=dscp)

        # Symbol name and instrument type columns will follow different orm paths depending on whether we got data from
        # all datasources or from a specified one.
        symbol_name_col = 'symbol__name' if datasource == 'all' else 'datasource_symbol__symbol__name'
        instrument_type_col = 'symbol__instrument_type' if datasource == 'all' else \
            'datasource_symbol__symbol__instrument_type'
        data = pd.DataFrame(
            list(metrics.values(symbol_name_col, instrument_type_col, 'first_candle_time', 'last_candle_time',
                                'minutes_min', 'minutes_max', 'minutes_avg', 'hours_min', 'hours_max', 'hours_avg',
                                'days_min', 'days_max', 'days_avg', 'weeks_min', 'weeks_max', 'weeks_avg',
                                'months_min', 'months_max', 'months_avg')))

        # Rename the symbol name and instrument type columns so they are the same across both sources
        data = data.rename(columns={symbol_name_col: 'Symbol', instrument_type_col: 'Instrument Type'})

        return data

    @staticmethod
    def get_aggregate_data(period: str, datasource: str, aggregation_period: str, from_date, to_date) -> pd.DataFrame:
        """
        Gets the aggregate data from the last batch for the specified period and datasoruce
        :param period: The candle period for the summary data
        :param datasource: The datasource for the candle data.
        :param aggregation_period. The aggregation period to aggregate the data to.
        :param from_date: Get aggregation from this date
        :param to_date: Get aggregation data to this date
        :return:
        """
        # Get the last available batch
        last_batch = BatchManager().last_available

        # Get the datasource candle period fo the selected datasource and period
        dscp = models.DataSourceCandlePeriod.objects.filter(datasource__name=datasource, period=period)[0]
        agg_qs = models.SummaryAggregation.objects.filter(summary_batch=last_batch, datasource_candleperiod=dscp,
                                                          aggregation_period=aggregation_period, time__gte=from_date,
                                                          time__lte=to_date)
        data = pd.DataFrame(list(agg_qs.values('datasource_symbol__symbol__name', 'time', 'num_candles', )))

        # Rename the symbol column
        data = data.rename(columns={'datasource_symbol__symbol__name': 'symbol'})

        return data


# Some methods used across all views
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

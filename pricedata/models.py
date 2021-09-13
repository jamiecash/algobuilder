import ast
import json
import logging

from django_celery_beat import models as cm
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


candle_periods = [
        ('1S', '1 Second'), ('5S', '5 Second'), ('10S', '10 Second'), ('15S', '15 Second'), ('30S', '30 Second'),
        ('1M', '1 Minute'), ('5M', '5 Minute'), ('10M', '10 Minute'), ('15M', '15 Minute'), ('30M', '30 Minute'),
        ('1H', '1 Hour'), ('3H', '3 Hour'), ('6H', '6 Hour'), ('12H', '12 Hour'), ('1D', '1 Day'), ('1W', '1 Week'),
        ('1MO', '1 Month')
    ]

instrument_types = [
        ('FOREX', 'Foreign Exchange'), ('CFD', 'Contract for Difference'), ('STOCK', 'Company Stock'),
        ('CRYPTO', 'Crypto Currency')
    ]

aggregation_periods = [
        ('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')
    ]

# Task repeat will be set depending on the candle period, so that we do not check for new candles more
# often than necessary. For periods < 10S, we will check every 10s. For others, we will align the
# repeat with the period.
schedules = {'1S': cm.IntervalSchedule(every=10, period=cm.IntervalSchedule.SECONDS),
             '5S': cm.IntervalSchedule(every=10, period=cm.IntervalSchedule.SECONDS),
             '10S': cm.IntervalSchedule(every=10, period=cm.IntervalSchedule.SECONDS),
             '15S': cm.IntervalSchedule(every=15, period=cm.IntervalSchedule.SECONDS),
             '30S': cm.IntervalSchedule(every=30, period=cm.IntervalSchedule.SECONDS),
             '1M': cm.CrontabSchedule(minute='*/1'), '5M': cm.CrontabSchedule(minute='*/5'),
             '10M': cm.CrontabSchedule(minute='*/10'), '15M': cm.CrontabSchedule(minute='*/15'),
             '30M': cm.CrontabSchedule(minute='*/30'), '1H': cm.CrontabSchedule(hour='*/1', minute=0),
             '3H': cm.CrontabSchedule(hour='*/3', minute=0), '6H': cm.CrontabSchedule(hour='*/6', minute=0),
             '12H': cm.CrontabSchedule(hour='*/12', minute=0), '1D': cm.CrontabSchedule(minute=0, hour=0),
             '1W': cm.CrontabSchedule(day_of_week='friday', hour=0, minute=0),
             '1MO':  cm.CrontabSchedule(day_of_month=1, hour=0, minute=0)}


class DataSource(models.Model):
    """
    A datasource to retrieve data from
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The datasource name
    name = models.CharField(max_length=20, unique=True)

    # The datasource plugin class
    pluginclass = models.ForeignKey('plugin.PluginClass', on_delete=models.CASCADE,
                                    limit_choices_to={'plugin_type': 'DataSourceImplementation'})

    # The datasource connection parameters
    connection_params = models.CharField(max_length=500)

    # Active.
    active = models.BooleanField(default=True)

    # The periodic task to refresh symbols
    task = models.OneToOneField(cm.PeriodicTask, on_delete=models.CASCADE,  null=True, blank=True)

    @property
    def task_name(self):
        """
        Returns the task name for retrieving symbols for this datasource
        :return:
        """
        return f'Updating symbols for {self.name}'

    def get_connection_param(self, param_name: str):
        """
        Returns the value of the specified connection param
        :return:
        """
        try:
            param_dict = ast.literal_eval(self.connection_params)
        except SyntaxError:
            msg = f"The string representation of a dict provided for connection params is invalid. " \
                  f"connection_params={self.connection_params}."
            self.__log.warning(msg)
            raise SyntaxError(msg)

        return param_dict[param_name]

    def setup_task(self):
        """
        Sets up the periodic task to refresh symbols. Also run it now.
        :return:
        """
        from pricedata import tasks  # Import here due to circular dependency.

        # Get the schedule from settings
        cron = json.loads(settings.ALGOBUILDER_PRICEDATA_SYMBOL_REFRESH_CRON)

        # Create the crontab schedule if it doesn't already exist
        schedule, created = cm.CrontabSchedule.objects.get_or_create(month_of_year=cron['month_of_year'],
                                                                     day_of_month=cron['day_of_month'],
                                                                     day_of_week=cron['day_of_week'],
                                                                     hour=cron['hour'], minute=cron['minute'])

        # Schedule
        self.task = cm.PeriodicTask.objects.create(
            name=self.task_name,
            task='retrieve_symbols',
            crontab=schedule,
            args=json.dumps([self.id])
        )
        self.save()

        # Run now
        tasks.retrieve_symbols.delay(datasource_id=self.id)

    def delete(self, *args, **kwargs):
        """
        Override delete to delete the symbol refresh scheduled task when we delete the datasource
        :param args:
        :param kwargs:
        :return:
        """
        if self.task is not None:
            self.task.delete()
        return super(self.__class__, self).delete(*args, **kwargs)

    def __repr__(self):
        return f"DataSource(name={self.name}, pluginclass={self.pluginclass}, " \
               f"connection_params={self.connection_params})"

    def __str__(self):
        return f"{self.name}"


class Symbol(models.Model):
    """
    A financial Symbol. e.g. GBPUSD
    """
    # Name of the symbol.
    name = models.CharField(max_length=50, unique=True)
    instrument_type = models.CharField(max_length=10, choices=instrument_types)

    def __repr__(self):
        return f"Symbol(name={self.name}, instrument_type={self.instrument_type})"

    def __str__(self):
        return f"{self.name}"


class DataSourceSymbol(models.Model):
    """
    The mapping between data sources and symbols, including a flag to determine whether price data will be retrieved
    from that datasource for the symbol.
    """

    datasource = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)

    # Flag to determine whether price data will be retrieved for this datasource / symbol combination
    retrieve_price_data = models.BooleanField(default=True)

    # Any broker specific data required for the symbol. Stored as json text.
    symbol_info = models.CharField(max_length=1000)

    @property
    def symbol_info_dict(self):
        """
        Returns the symbol info as a dict.
        :return: A dict of symbol_info. None if symbol info is empty
        """
        symbol_info = None
        if len(self.symbol_info) > 0:
            symbol_info = json.loads(self.symbol_info)

        return symbol_info

    def __repr__(self):
        return f"DataSourceSymbol(datasource={self.datasource}, symbol={self.symbol}, " \
               f"retrieve_price_data={self.retrieve_price_data})"

    def __str__(self):
        return f"datasource={self.datasource}, symbol={self.symbol}, retrieve_price_data={self.retrieve_price_data}"

    class Meta:
        unique_together = ('datasource', 'symbol',)


class DataSourceCandlePeriod(models.Model):
    """
    The candle periods that will be used to retrieve price data from a datasource.
    """
    datasource = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    period = models.CharField(max_length=3, choices=candle_periods)

    # The first date that the candle will be retrieved from
    start_from = models.DateTimeField()

    # Whether data collection is active
    active = models.BooleanField(default=False)

    # The periodic task to refresh prices
    task = models.OneToOneField(cm.PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)

    @property
    def task_name(self):
        """
        Returns the task name for retrieving prices for this datasource candle period
        :return:
        """
        return f'Updating {self.period} prices for {self.datasource.name}'

    def setup_task(self):
        """
        Sets up the periodic task to refresh prices. Also run it now.
        :return:
        """

        # Get the schedule from the period
        schedule = schedules[self.period]

        # Schedule. We may have an interval schedule or a crontab schedule
        if isinstance(schedule, cm.IntervalSchedule):
            # Get or create the schedule
            schedule, created = cm.IntervalSchedule.objects.get_or_create(every=schedule.every, period=schedule.period)
            schedule.save()

            # Create the task
            self.task = cm.PeriodicTask.objects.create(
                name=self.task_name,
                task='retrieve_prices',
                interval=schedule,
                args=json.dumps([self.id])
            )
        elif isinstance(schedule, cm.CrontabSchedule):
            # Get or create the schedule
            schedule, created = cm.CrontabSchedule.objects.get_or_create(hour=schedule.hour, minute=schedule.minute,
                                                                         day_of_week=schedule.day_of_week,
                                                                         day_of_month=schedule.day_of_month)
            schedule.save()

            # Create the task
            self.task = cm.PeriodicTask.objects.create(
                name=self.task_name,
                task='retrieve_prices',
                crontab=schedule,
                args=json.dumps([self.id])
            )

        self.save()

    def delete(self, *args, **kwargs):
        """
        Override delete to delete the price refresh scheduled task when we delete the datasourcecandleperiod
        :param args:
        :param kwargs:
        :return:
        """
        if self.task is not None:
            self.task.delete()
        return super(self.__class__, self).delete(*args, **kwargs)

    def __repr__(self):
        return f"DataSourceCandlePeriod(datasource={self.datasource}, period={self.period}, " \
               f"start_from={self.start_from}, active={self.active})"

    def __str__(self):
        return f"datasource={self.datasource}, period={self.period}"

    class Meta:
        unique_together = ('datasource', 'period',)


class Candle(models.Model):
    """
    1 OHLC candles for the Symbol retrieved from the DataSource
    """
    # The datasource that this was retrieved from and the symbol that it is for
    datasource_symbol = models.ForeignKey(DataSourceSymbol, on_delete=models.CASCADE)

    # Timestamp
    time = models.DateTimeField()

    # Period for the candle
    period = models.CharField(max_length=3, choices=candle_periods)

    # OHLC columns for bid and ask
    bid_open = models.DecimalField(max_digits=12, decimal_places=6)
    bid_high = models.DecimalField(max_digits=12, decimal_places=6)
    bid_low = models.DecimalField(max_digits=12, decimal_places=6)
    bid_close = models.DecimalField(max_digits=12, decimal_places=6)
    ask_open = models.DecimalField(max_digits=12, decimal_places=6)
    ask_high = models.DecimalField(max_digits=12, decimal_places=6)
    ask_low = models.DecimalField(max_digits=12, decimal_places=6)
    ask_close = models.DecimalField(max_digits=12, decimal_places=6)

    # Volume of ticks that made up candle
    volume = models.IntegerField()

    def __repr__(self):
        return f"Candle(datasource_symbol={self.datasource_symbol}, time={self.time}, period={self.period}, " \
               f"bid_open={self.bid_open}, bid_high={self.bid_high}, bid_low={self.bid_low}, " \
               f"bid_close={self.bid_close}, ask_open={self.ask_open}, ask_high={self.ask_high}, " \
               f"ask_low={self.ask_low}, ask_close={self.ask_close}, volume={self.volume})"

    def __str__(self):
        return f"datasource={self.datasource_symbol.datasource}, symbol={self.datasource_symbol.symbol}, " \
               f"time={self.time}, period={self.period}, " \
               f"bid_open={self.bid_open}, bid_high={self.bid_high}, bid_low={self.bid_low}, " \
               f"bid_close={self.bid_close}, ask_open={self.ask_open}, ask_high={self.ask_high}, " \
               f"ask_low={self.ask_low}, ask_close={self.ask_close}, volume={self.volume}"

    class Meta:
        unique_together = ('datasource_symbol', 'time', 'period',)


class SummaryBatch(models.Model):
    """
    A batch run to create the price data quality metrics and aggregation data for the pricedata quality dashboards
    """
    STATUS_NOT_STARTED = 'NOT_STARTED'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETE = 'COMPLETE'

    # We need the time of the batch and the batch type
    time = models.DateTimeField(unique=True)

    # And a status
    status = models.CharField(max_length=11, choices=[(STATUS_NOT_STARTED, STATUS_NOT_STARTED),
                                                      (STATUS_IN_PROGRESS, STATUS_IN_PROGRESS),
                                                      (STATUS_COMPLETE, STATUS_COMPLETE)],
                              default=STATUS_NOT_STARTED)


class SummaryMetric(models.Model):
    """
    A single metric. For each SummaryBatch run for METRICS, we will create metrics containing:
        * The datasource candle period;
        * The datetime of the first and last candles for each datasource / period;
        * The number of candles for each datasource / period; and
        * The minimum, maximum and average number of candles for each aggregation period for each datasource / period.
    """
    # The batch datasource / period and symbol
    summary_batch = models.ForeignKey(SummaryBatch, on_delete=models.CASCADE)
    datasource_candleperiod = models.ForeignKey(DataSourceCandlePeriod, on_delete=models.CASCADE)
    datasource_symbol = models.ForeignKey(DataSourceSymbol, on_delete=models.CASCADE)

    # First and last candles available for the datasource / period and the number of candles
    first_candle_time = models.DateTimeField()
    last_candle_time = models.DateTimeField()
    num_candles = models.BigIntegerField()

    # Min, max and avg for each aggregation period
    minutes_min = models.BigIntegerField()
    minutes_max = models.BigIntegerField()
    minutes_avg = models.BigIntegerField()

    hours_min = models.BigIntegerField()
    hours_max = models.BigIntegerField()
    hours_avg = models.BigIntegerField()

    days_min = models.BigIntegerField()
    days_max = models.BigIntegerField()
    days_avg = models.BigIntegerField()

    weeks_min = models.BigIntegerField()
    weeks_max = models.BigIntegerField()
    weeks_avg = models.BigIntegerField()

    months_min = models.BigIntegerField()
    months_max = models.BigIntegerField()
    months_avg = models.BigIntegerField()

    class Meta:
        unique_together = ('summary_batch', 'datasource_candleperiod', 'datasource_symbol',)


class SummaryMetricAllDatasources(models.Model):
    """
    The summary metrics calculated across all datasources for each candle period
    """
    # The batch, period and symbol
    summary_batch = models.ForeignKey(SummaryBatch, on_delete=models.CASCADE)
    period = models.CharField(max_length=3, choices=candle_periods)
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)

    # First and last candles available across all datasources for period, and the number of candles for the period
    first_candle_time = models.DateTimeField()
    last_candle_time = models.DateTimeField()
    num_candles = models.BigIntegerField()

    # Min, max and avg for each aggregation period
    minutes_min = models.BigIntegerField()
    minutes_max = models.BigIntegerField()
    minutes_avg = models.BigIntegerField()

    hours_min = models.BigIntegerField()
    hours_max = models.BigIntegerField()
    hours_avg = models.BigIntegerField()

    days_min = models.BigIntegerField()
    days_max = models.BigIntegerField()
    days_avg = models.BigIntegerField()

    weeks_min = models.BigIntegerField()
    weeks_max = models.BigIntegerField()
    weeks_avg = models.BigIntegerField()

    months_min = models.BigIntegerField()
    months_max = models.BigIntegerField()
    months_avg = models.BigIntegerField()

    class Meta:
        unique_together = ('summary_batch', 'period', 'symbol',)


class SummaryAggregation(models.Model):
    """
    The number of candles retrieved for each symbol / aggregation period by time
    """

    # The batch and datasource / period
    summary_batch = models.ForeignKey(SummaryBatch, on_delete=models.CASCADE)
    datasource_candleperiod = models.ForeignKey(DataSourceCandlePeriod, on_delete=models.CASCADE)

    # Time, symbol, aggregation period and count
    time = models.DateTimeField()
    datasource_symbol = models.ForeignKey(DataSourceSymbol, on_delete=models.CASCADE)
    aggregation_period = models.CharField(max_length=7, choices=aggregation_periods)
    num_candles = models.BigIntegerField()

    class Meta:
        unique_together = ('summary_batch', 'datasource_candleperiod', 'time', 'datasource_symbol',
                           'aggregation_period')


@receiver(post_save, sender=DataSource)
def save_datasource_receiver(sender, instance, created, **kwargs):
    if created:
        instance.setup_task()
    else:
        if instance.task is not None:
            instance.task.enabled = instance.active
            instance.task.save()


@receiver(post_save, sender=DataSourceCandlePeriod)
def save_datasourcecandleperiod_receiver(sender, instance, created, **kwargs):
    if created:
        instance.setup_task()
    else:
        if instance.task is not None:
            instance.task.enabled = instance.active
            instance.task.save()

import ast
import json
import logging

from django.utils import timezone
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.db import models
from django.db.models.signals import post_delete
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

    def save(self, *args, **kwargs):
        """
        Override save to update symbols from datasource every day
        :param args:
        :param kwargs:
        :return:
        """
        super().save(*args, **kwargs)

        # Schedule to run every day. We will use get or create to ensure we don't duplicate schedules
        # or tasks.
        schedule, created = IntervalSchedule.objects.get_or_create(every=1, period=IntervalSchedule.DAYS)

        # Don't reschedule of we already have this task set up
        task_name = f'Updating symbols for {self.name}'
        tasks = PeriodicTask.objects.filter(name=task_name)
        if len(tasks) == 0:
            PeriodicTask.objects.create(interval=schedule, name=task_name, task='pricedata.tasks.retrieve_symbols',
                                        start_time=timezone.now(), kwargs=json.dumps({'datasource_id': self.id}))

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

    def save(self, *args, **kwargs):
        """
        Override save start the retriever if active.
        :param args:
        :param kwargs:
        :return:
        """
        super().save(*args, **kwargs)

        # Task repeat will be set depending on the candle period, so that we do not check for new candles more
        # often than necessary. For periods < 10S, we will check every 10S. For others, we will align the
        # repeat with the period.
        candle_period_repeats = {'1S': (10, IntervalSchedule.SECONDS), '5S': (10, IntervalSchedule.SECONDS),
                                 '10S': (10, IntervalSchedule.SECONDS), '15S': (15, IntervalSchedule.SECONDS),
                                 '30S': (30, IntervalSchedule.SECONDS), '1M': (1, IntervalSchedule.MINUTES),
                                 '5M': (5, IntervalSchedule.MINUTES), '10M': (10, IntervalSchedule.MINUTES),
                                 '15M': (15, IntervalSchedule.MINUTES), '30M': (30, IntervalSchedule.MINUTES),
                                 '1H': (1, IntervalSchedule.HOURS), '3H': (3, IntervalSchedule.HOURS),
                                 '6H': (6, IntervalSchedule.HOURS), '12H': (12, IntervalSchedule.HOURS),
                                 '1D': (1, IntervalSchedule.DAYS), '1W': (7, IntervalSchedule.DAYS),
                                 '1MO': (30, IntervalSchedule.DAYS)}

        # Get or create schedule.
        repeat = candle_period_repeats[self.period]
        schedule, created = IntervalSchedule.objects.get_or_create(every=repeat[0], period=repeat[1])

        # Don't reschedule of we already have this task set up
        task_name = f"Retrieving prices for DataSourceCandlePeriod id {self.id}."
        tasks = PeriodicTask.objects.filter(name=task_name)
        if len(tasks) == 0:
            PeriodicTask.objects.create(interval=schedule, name=task_name, task='pricedata.tasks.retrieve_prices',
                                        start_time=timezone.now(),
                                        kwargs=json.dumps({'datasource_candleperiod_id': self.id}))

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


# Receiver to delete task when DataSourceCandlePeriod is deleted
@receiver(post_delete, sender=DataSourceCandlePeriod)
def delete_datasourcecandleperiod_receiver(sender, instance, using, **kwargs):
    task_name = f"Retrieving prices for DataSourceCandlePeriod id {instance.id}."
    task = PeriodicTask.objects.filter(name=task_name)[0]
    task.delete()

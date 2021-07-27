import ast
import logging

from django.db import models

from background_task.models import Task
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
        Override save to import requirements listed in requirements_file and test the connection.
        :param args:
        :param kwargs:
        :return:
        """
        super().save(*args, **kwargs)

        import pricedata.tasks as tasks  # Import here due to circular dependency.

        # Check if task is already scheduled
        task_name = f"retrieve_symbols for DataSource id {self.id}."
        scheduled_tasks = Task.objects.filter(verbose_name=task_name)

        # If not already scheduled then schedule background task to configure data source. Repeat daily.
        if len(scheduled_tasks) == 0:
            tasks.DataRetriever.retrieve_symbols(datasource_id=self.id, verbose_name=task_name, repeat=60*60*24,
                                                 repeat_until=None)

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

        import pricedata.tasks as tasks  # Import here due to circular dependency.

        # Check if task is already scheduled
        task_name = f"retrieve_prices for DataSourceCandlePeriod id {self.id}."
        scheduled_tasks = Task.objects.filter(verbose_name=task_name)

        # If not already scheduled then schedule background task to retrieve the data.
        if len(scheduled_tasks) == 0:
            # Task repeat will be set depending on the candle period, so that we do not check for new candles more
            # often than necessary. For periods < 10S, we will check every 10S. For others, we will align the
            # repeat with the period.
            candle_period_repeats = {'1S': 10, '5S': 10, '10S': 10, '15S': 15, '30S': 30, '1M': 60, '5M': 60 * 5,
                                     '10M': 60 * 10, '15M': 60 * 15, '30M': 60 * 30, '1H': 60 * 60, '3H': 60 * 60 * 3,
                                     '6H': 60 * 60 * 6, '12H': 60 * 60 * 12, '1D': 60 * 60 * 24, '1W': 60 * 60 * 24 * 7,
                                     '1MO': 60 * 60 * 24 * 7 * 4}
            tasks.DataRetriever.retrieve_prices(datasource_candleperiod_id=self.id, verbose_name=task_name,
                                                repeat=candle_period_repeats[self.period], repeat_until=None)

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
    task_name = f"retrieve_prices for DataSourceCandlePeriod id {instance.id}."
    task = Task.objects.get(verbose_name=task_name)
    task.delete()

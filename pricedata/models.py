import ast
import datetime
import logging

from django.db import models


candle_periods = [
        ('1S', '1 Second'),
        ('5S', '5 Second'),
        ('10S', '10 Second'),
        ('15S', '15 Second'),
        ('30S', '30 Second'),
        ('1M', '1 Minute'),
        ('5M', '5 Minute'),
        ('10M', '10 Minute'),
        ('15M', '15 Minute'),
        ('30M', '30 Minute'),
        ('1H', '1 Hour'),
        ('3H', '3 Hour'),
        ('6H', '6 Hour'),
        ('12H', '12 Hour'),
        ('1D', '1 Day'),
        ('1W', '1 Week'),
        ('1MO', '1 Month')
    ]


class DataSource(models.Model):
    """
    A datasource to retrieve data from
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The datasource name
    name = models.CharField(max_length=20, unique=True)

    # The datasource implementation class
    module = models.FileField(max_length=200, upload_to=r'pricedata\datasources')
    class_name = models.CharField(max_length=20)

    # The requirements.txt file containing any dependencies
    requirements_file = models.FileField(max_length=200, upload_to=r'pricedata\datasources')

    # The datasource connection parameters
    connection_params = models.CharField(max_length=500)

    def get_connection_param(self, param_name: str):
        """
        Returns the value of the specified connection param
        :return:
        """
        return ast.literal_eval(self.connection_params)[param_name]

    def save(self, *args, **kwargs):
        """
        Override save to import requirements listed in requirements_file and test the connection.
        :param args:
        :param kwargs:
        :return:
        """
        super().save(*args, **kwargs)

        # Configure new datasource
        from pricedata.datasource import DataSourceImplementation  # Import here due to circular dependency
        DataSourceImplementation.configure(datasource=self)

    def __repr__(self):
        return f"DataSource(name={self.name}, module={self.module}, class={self.class_name}, " \
               f"requirements_file={self.requirements_file}, connection_params={self.connection_params})"

    def __str__(self):
        return f"{self.name}"


class Symbol(models.Model):
    """
    A financial Symbol. e.g. GBPUSD
    """
    # Name of the symbol.
    name = models.CharField(max_length=50, unique=True)
    instrument_type = models.CharField(max_length=10, choices=[
        ('FOREX', 'Foreign Exchange'),
        ('CFD', 'Contract for Difference'),
        ('STOCK', 'Company Stock'),
        ('CRYPTO', 'Crypto Currency')
    ])

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


class DataSourceCandlePeriod(models.Model):
    """
    The candle periods that will be used to retrieve price data from a datasource.
    """
    datasource = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    period = models.CharField(max_length=3, choices=candle_periods)

    # The first date that the candle will be retrieved from
    start_from = models.DateTimeField(default=datetime.datetime.now())

    # Whether data collection is active
    active = models.BooleanField(default=False)

    def __repr__(self):
        return f"DataSourceCandlePeriod(datasource={self.datasource}, period={self.period}, " \
               f"start_from={self.start_from}, active={self.active})"

    def __str__(self):
        return f"datasource={self.datasource}, period={self.period}"


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

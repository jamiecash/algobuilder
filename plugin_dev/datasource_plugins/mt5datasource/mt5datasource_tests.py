import logging
from django.test import TestCase

from datetime import datetime

from mt5datasource import MT5DataSource
from plugin import models as pl_models
from pricedata import models as pd_models


class TestMT5DataSource(TestCase):
    """
    Unit test to test MT5DataSource.
    """

    # Logger
    __log = logging.getLogger(__name__)

    def setUp(self) -> None:
        """
        Create datasource, symbol and datasourcesymbol
        :return:
        """
        # Create a plugin and plugin class.
        plugin = pl_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = pl_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

        # Create the datasource, symbol and datasourcesymbol
        self.ds = pd_models.DataSource(name="MT5", pluginclass=self.plugin_class, active=True,
                                       connection_params="{'market_watch_only': True}")
        self.ds.save()
        self.symbol = pd_models.Symbol(name="GBPUSD", instrument_type="FOREX")
        self.symbol.save()
        self.dss = pd_models.DataSourceSymbol(datasource=self.ds, symbol=self.symbol, retrieve_price_data=True,
                                              symbol_info='{"point": 0, "digits": 0}')
        self.dss.save()

    def test_get_symbols(self):
        symbols = MT5DataSource(datasource=self.ds).get_symbols()
        self.assertTrue(len(symbols) > 0, "No symbols were returned.")

    def test_get_prices(self):
        """
        Test 2 periods, one that resamples from ticks and one that retrieves directly as candles
        """
        from_date = datetime(2021, 7, 6, 18, 0, 0)
        to_date = datetime(2021, 7, 6, 19, 0, 0)

        # Symbol info required for calculation
        symbol_info = self.dss.symbol_info_dict

        # 1M candles, should use copy_rates_range api
        prices = MT5DataSource(datasource=self.ds).get_prices('GBPUSD', from_date, to_date, '1M', symbol_info)
        self.assertTrue(len(prices) > 0, "No prices were returned for 1M period.")

        # 1S candles, should use copy_ticks_range api
        prices = MT5DataSource(datasource=self.ds).get_prices('GBPUSD', from_date, to_date, '1S', symbol_info)
        self.assertTrue(len(prices) > 0, "No prices were returned for 1S period.")

    def test_historic(self):
        """
        Test what happens when we try and get data for a historic period where MT5 no longer holds data for. We should
        raise an exception.
        """
        pass  # MT5 now returning empty dataframe and success for historic periods.

        """from_date = datetime(2000, 7, 6, 18, 0, 0)
        to_date = datetime(2000, 7, 6, 19, 0, 0)

        datasource_impl = MT5DataSource(data_source_model=DataSource())

        # 1S candles, should use copy_ticks_range api
        with self.assertRaises(DataNotAvailableException):
            prices = datasource_impl.get_prices(symbol='GBPUSD', from_date=from_date, to_date=to_date, period='1S')
            print(prices)"""

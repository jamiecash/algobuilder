from decimal import Decimal

import pandas as pd

from background_task import models as task_model
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock

from plugin import models as plugin_models
from pricedata import models
from pricedata import tasks


# Tests for the data model
class DataSourceTests(TestCase):

    plugin_class = None

    def setUp(self) -> None:
        # Create a plugin and plugin class for use in these tests
        plugin = plugin_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = plugin_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

    def test_get_connection_param(self):
        """
        get_connection_param returns a data source connection param passed as a string representation of a dict. Test
        that it works for both string and int params and test that badly formatted connection params are handled
        elegantly.
        """

        # Test valid str and int params
        connection_params = "{'str_param': 'str_val', 'int_param': 7}"
        ds = models.DataSource(connection_params=connection_params)
        self.assertEqual(ds.get_connection_param('str_param'), 'str_val')
        self.assertEqual(ds.get_connection_param('int_param'), 7)

        # Test badly formatted connection params string. We will miss the closing ' on the first param name
        connection_params = "{'str_param: 'str_val', 'int_param': 7}"
        ds = models.DataSource(connection_params=connection_params)
        self.assertRaises(SyntaxError, ds.get_connection_param, ['str_param'])

    def test_save(self):
        """
        When a datasource is saved, it should call DataSourceImplementation.configure passing itself. We will test
        using a mock DataSourceImplementation.
        :return:
        """

        # Create datasource with a name that we can test and save it
        ds = models.DataSource(name='test', pluginclass=self.plugin_class)
        ds.save()

        # Test that a task was created to configure this datasource
        task_name = f"retrieve_symbols for DataSource id {ds.id}."

        # Check that task exists
        task = task_model.Task.objects.get(verbose_name=task_name)
        self.assertIsNotNone(task)


class DataSourceCandlePeriodTests(TestCase):
    plugin_class = None

    def setUp(self) -> None:
        # Create a plugin and plugin class for use in these tests
        plugin = plugin_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = plugin_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

    def test_save_and_delete(self):
        """
        When a datasourcecandleperiod is saved, it should schedule a task to load its symbols.
        :return:
        """

        # Create and save a datasourcecandleperiod. This will require us to create a datasource.
        ds = models.DataSource(name='test', pluginclass=self.plugin_class)
        ds.save()
        dscp = models.DataSourceCandlePeriod(datasource=ds, period='1S', active=True, start_from=timezone.now())
        dscp.save()

        # Task name to check
        task_name = f"retrieve_prices for DataSourceCandlePeriod id {dscp.id}."

        # Check that task exists
        task = task_model.Task.objects.get(verbose_name=task_name)
        self.assertIsNotNone(task)

        # Delete the task
        dscp.delete()

        # Check that task no longer exists
        num_tasks = len(task_model.Task.objects.filter(verbose_name=task_name))
        self.assertTrue(num_tasks == 0)


# Tests for tasks
class DataRetrieverTests(TestCase):
    plugin_class = None

    def setUp(self) -> None:
        # Create a plugin and plugin class for use in these tests
        plugin = plugin_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = plugin_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

    @patch('pricedata.datasource.DataSourceImplementation')
    def test_retrieve_symbols(self, mock):
        # Create some mock symbols
        mock_symbols = []
        for i in range(0, 5):
            mock_symbols.append({'symbol_name': f"Symbol{i}", 'instrument_type': 'FOREX'})

        # Mock the instance method of DataSourceImplementation to return a new mock
        datasource_subclass_mock = MagicMock()
        mock.instance.return_value = datasource_subclass_mock

        # Mock the subclasses get_symbols method to return our mock symbols
        datasource_subclass_mock.get_symbols.return_value = mock_symbols

        # Create a data source
        ds = models.DataSource(id=5, name='test', pluginclass=self.plugin_class)
        ds.save()

        # Run retrieve_symbols_impl. We should have the mock symbols populated for all 5 symbols.
        tasks.DataRetriever.retrieve_symbols_impl(datasource_id=ds.id)
        symbols = models.Symbol.objects.all()
        self.assertTrue(len(symbols) == 5)

    @patch('pricedata.datasource.DataSourceImplementation')
    def test_retrieve_prices(self, mock):
        # Create some mock prices in a dataframe
        columns = ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close', 'ask_open', 'ask_high',
                   'ask_low', 'ask_close', 'volume']
        data = []
        for i in range(0, 5):
            data.append([timezone.now() + timedelta(seconds=i), '1S', i, i, i, i, i, i, i, i, i])
        mock_prices = pd.DataFrame(columns=columns, data=data)

        # Mock the instance method of DataSourceImplementation to return a new mock
        datasource_subclass_mock = MagicMock()
        mock.instance.return_value = datasource_subclass_mock

        # Mock the subclasses get_prices method to return our mock dataframe
        datasource_subclass_mock.get_prices.return_value = mock_prices

        # Create a data source and datasourcecandleperiod model.
        ds = models.DataSource(id=5, name='test', pluginclass=self.plugin_class)
        ds.save()
        dscp = models.DataSourceCandlePeriod(datasource=ds, period='1S', start_from=timezone.now(), active=True)
        dscp.save()

        # Create some symbols and datasourcesymbols
        for i in range(0, 5):
            symbol = models.Symbol(name=f'Symbol{i}')
            symbol.save()
            ds_symbol = models.DataSourceSymbol(datasource=ds, symbol=symbol, retrieve_price_data=True)
            ds_symbol.save()

        # Run retrieve_prices_impl. We should have the mock data populated for all symbols. 25 in total, 5 rows for
        # 5 symbols
        tasks.DataRetriever.retrieve_prices_impl(datasource_candleperiod_id=dscp.id)
        candles = models.Candle.objects.all()
        self.assertEquals(len(candles), 25)

    @patch('pricedata.datasource.DataSourceImplementation')
    def test_existing_prices(self, mock):
        """
        Test that prices that already exist in DB are updated rather than inserted
        """
        # Create some mock prices in a dataframe
        columns = ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close', 'ask_open', 'ask_high',
                   'ask_low', 'ask_close', 'volume']
        data = []
        for i in range(0, 5):
            amt = Decimal(i)
            data.append([timezone.now() + timedelta(seconds=i), '1S', amt, amt, amt, amt, amt, amt, amt, amt, i])
        mock_prices = pd.DataFrame(columns=columns, data=data)

        # Mock the instance method of DataSourceImplementation to return a new mock
        datasource_subclass_mock = MagicMock()
        mock.instance.return_value = datasource_subclass_mock

        # Mock the subclasses get_prices method to return our mock dataframe
        datasource_subclass_mock.get_prices.return_value = mock_prices

        # Create a data source and datasourcecandleperiod model.
        ds = models.DataSource(id=5, name='test', pluginclass=self.plugin_class)
        ds.save()
        dscp = models.DataSourceCandlePeriod(datasource=ds, period='1S', start_from=timezone.now(), active=True)
        dscp.save()

        # Create symbol and datasourcesymbols
        symbol = models.Symbol(name=f'TestSymbol')
        symbol.save()
        ds_symbol = models.DataSourceSymbol(datasource=ds, symbol=symbol, retrieve_price_data=True)
        ds_symbol.save()

        # Run retrieve_prices_impl. We should have the mock data populated for symbols. 5 prices
        tasks.DataRetriever.retrieve_prices_impl(datasource_candleperiod_id=dscp.id)

        # Run it again. These should be duplicate, so should be updated.
        tasks.DataRetriever.retrieve_prices_impl(datasource_candleperiod_id=dscp.id)

        # We should have 5 candles as the first 5 should have been updated
        candles = models.Candle.objects.all()
        self.assertEquals(len(candles), 5)


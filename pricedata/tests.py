import datetime
from decimal import Decimal

import pandas as pd

from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock

from django_celery_beat.models import PeriodicTask

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

    def test_save_and_delete(self):
        """
        When a datasource is saved, it should schedule a task to retrieve symbols. When it is deleted, its task should
        also be deleted.
        :return:
        """

        # Create datasource with a name that we can test and save it
        ds = models.DataSource(name='test', pluginclass=self.plugin_class)
        ds.save()

        # Test that a task was created to configure this datasource
        task_name = ds.task_name

        # Check that task exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertGreater(len(task_list), 0)

        # Delete the datasource
        ds.delete()

        # Check that the task no longer exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertEqual(len(task_list), 0)


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
        task_name = dscp.task_name

        # Check that task exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertGreater(len(task_list), 0)

        # Delete the datasource candleperiod. This should delete the task
        dscp.delete()

        # Check that task no longer exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertEqual(len(task_list), 0)


# Tests for tasks
class TasksTest(TestCase):
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

        # Run retrieve_symbols. We should have the mock symbols populated for all 5 symbols.
        tasks.retrieve_symbols(datasource_id=ds.id)
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

        # Run retrieve_prices. We should have the mock data populated for all symbols. 25 in total, 5 rows for
        # 5 symbols
        tasks.retrieve_prices(datasource_candleperiod_id=dscp.id)
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

        # Run retrieve_prices. We should have the mock data populated for symbols. 5 prices
        tasks.retrieve_prices(datasource_candleperiod_id=dscp.id)

        # Run it again. These should be duplicate, so should be updated.
        tasks.retrieve_prices(datasource_candleperiod_id=dscp.id)

        # We should have 5 candles as the first 5 should have been updated
        candles = models.Candle.objects.all()
        self.assertEquals(len(candles), 5)

    def test_summary_data(self):
        """
        Test that the summary data accurately reflects the candle data
        :return:
        """

        # Create 10 symbols
        for symbol_name in [f'SYMBOL_{i}' for i in range(0, 10)]:
            symbol = models.Symbol(name=symbol_name, instrument_type='FOREX')
            symbol.save()

        # Create 3 datasources, each with 3 candle periods. Each datasource will have all symbols
        datasources = []
        for i in range(0, 3):
            ds = models.DataSource(name=f'DS{i}', pluginclass=self.plugin_class, connection_params={'a': i})
            ds.save()
            for period in ['1S', '1M', '1H']:
                dscp = models.DataSourceCandlePeriod(datasource=ds, period=period, start_from=timezone.now())
                dscp.save()

            for symbol in models.Symbol.objects.all():
                dss = models.DataSourceSymbol(datasource=ds, symbol=symbol, retrieve_price_data=True)
                dss.save()

                # Create 1000 prices for every symbol for every period, 1 second apart
                now = timezone.now()
                for j in range(0, 1000):
                    for period in ['1S', '1M', '1H']:
                        candle = models.Candle(datasource_symbol=dss, time=now + timedelta(seconds=j),
                                               period=period, bid_open=j, bid_high=j, bid_low=j, bid_close=j,
                                               ask_open=j, ask_close=j, ask_high=j, ask_low=j, volume=j)
                        candle.save()

        # Run the task
        tasks.create_summary_data()

        # We should have a summary batch
        batches = models.SummaryBatch.objects.all()
        self.assertEqual(len(batches), 1)
        batch = batches[0]

        # We should have 90 summary metric records, 10 symbols * 3 datasources * 3 periods
        metrics = models.SummaryMetric.objects.filter(summary_batch=batch)
        self.assertEqual(len(metrics), 90)

        # We should have 30 datasource metrics, 10 symbols * 3 periods
        ds_metrics = models.SummaryMetricAllDatasources.objects.filter(summary_batch=batch)
        self.assertEqual(len(ds_metrics), 30)

        # For the 1S candleperiod for a datasource, for the minutes aggregation period we should have 170 or 180 rows
        # (1000 seconds will span 17 or 18 minutes depending on whether we start at a minute rollover * 10 symbols)
        dscp = models.DataSourceCandlePeriod.objects.filter(period='1S')[0]
        aggregations = models.SummaryAggregation.objects.filter(summary_batch=batch, datasource_candleperiod=dscp,
                                                                aggregation_period='minutes')
        self.assertTrue(len(aggregations) in [170, 180])

        # For a single symbol we will have 17 or 18
        dss = models.DataSourceSymbol.objects.all()[0]
        aggregations = models.SummaryAggregation.objects.filter(summary_batch=batch, datasource_candleperiod=dscp,
                                                                aggregation_period='minutes', datasource_symbol=dss)
        self.assertTrue(len(aggregations) in [17, 18])

        # For any of these, except for the first or last, the minute aggregation columns should all be 60 as we
        # populated a price for every second.
        self.assertEquals(aggregations[1].num_candles, 60)


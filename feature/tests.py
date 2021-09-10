from random import random

from django.test import TestCase
from django_celery_beat.models import PeriodicTask
from plugin import models as plugin_models
from feature import models
from pricedata import models as pd_models
from datetime import datetime, timedelta
import pytz
from feature import feature as ft


class FeatureExecutionTests(TestCase):
    plugin_class = None

    def setUp(self) -> None:
        # Create a plugin and plugin class for use in these tests
        plugin = plugin_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = plugin_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

    def test_save_and_delete(self):
        """
        When a feature execution is saved, it should schedule a periodic task to run it.
        :return:
        """

        # Create and save a feature. This is required for a feature execution
        feature = models.Feature(name="test_feature", pluginclass=self.plugin_class, active=True)
        feature.save()

        # Create and save a feature execution
        feature_execution = models.FeatureExecution(feature=feature, candle_period='1S',
                                                    calculation_period='1D', active=True)
        feature_execution.save()

        # Task name to check
        task_name = feature_execution.task_name

        # Check that task exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertGreater(len(task_list), 0)

        # Delete the feature execution. This should delete the task
        feature_execution.delete()

        # Check that task no longer exists
        task_list = PeriodicTask.objects.filter(name=task_name)
        self.assertIsNotNone(task_list)
        self.assertEqual(len(task_list), 0)


class FeatureImplementationTests(TestCase):
    """
    Tests the utility methods available in FeatureImplementation, the base class for features
    """

    def setUp(self) -> None:
        """
        Create a datasource, symbol, candles and feature
        :return:
        """
        # Create a plugin and plugin class. We can use this for both the datasource and feature as it isnt part of what
        # we are testing
        plugin = plugin_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = plugin_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
        self.plugin_class.save()

        # Create the datasource and symbol
        ds = pd_models.DataSource(name="test_ds", pluginclass=self.plugin_class, active=True)
        ds.save()
        symbol = pd_models.Symbol(name="test", instrument_type="FOREX")
        symbol.save()
        self.dss = pd_models.DataSourceSymbol(datasource=ds, symbol=symbol, retrieve_price_data=True)
        self. dss.save()

        # Create 1000 1S candles
        time = datetime(2020, 1, 1, 0, 0, 0, 0, pytz.UTC)
        for i in range(0, 1000):
            price = random()
            time = time + timedelta(seconds=1)
            candle = pd_models.Candle(datasource_symbol=self.dss, time=time, period='1S', bid_open=price,
                                      bid_high=price, bid_low=price, bid_close=price, ask_open=price, ask_high=price,
                                      ask_low=price, ask_close=price, volume=i)
            candle.save()

        # Create a feature, feature execution and feature execution symbol
        feature = models.Feature(name="test_feature", pluginclass=self.plugin_class)
        feature.save()
        self.feature_execution = models.FeatureExecution(feature=feature, candle_period='1S', calculation_period='1M')
        self.feature_execution.save()
        feature_execution_dss = models.FeatureExecutionDataSourceSymbol(feature_execution=self.feature_execution,
                                                                        datasource_symbol=self.dss)
        feature_execution_dss.save()

    def test_get_data_from_date(self):
        """
        Test that the from date gets the first date available for a candle when no features have been calculated, and
        the next available date - calculation period when they have.
        :return:
        """
        # Get the data from date. As we haven't calculated any features, this should be 2020-01-01 00:00:01
        from_date = ft.FeatureImplementation.get_data_from_date(feature_execution=self.feature_execution)
        self.assertEqual(from_date, datetime(2020, 1, 1, 0, 0, 1, 0, pytz.UTC))

        # Now add a feature calculation result for the 5 minutes (300 rows)
        time = datetime(2020, 1, 1, 0, 0, 0, 0, pytz.UTC)
        for i in range(0, 300):
            calc = random()
            time = time + timedelta(seconds=1)
            fexr = models.FeatureExecutionResult(feature_execution=self.feature_execution, time=time, result=calc)
            fexr.save()

        # Get the data from date. We have calculated results for the 5 minutes amd the calculation period is 1 minute,
        # so this should be 2020-01-01 00:04:01
        from_date = ft.FeatureImplementation.get_data_from_date(feature_execution=self.feature_execution)
        self.assertEqual(from_date, datetime(2020, 1, 1, 0, 4, 1, 0, pytz.UTC))

    def test_get_data(self):
        # Get the data for the first symbol (we only have 1). As we haven't calculated any features, this should
        # contain all 1000 rows of candle data
        data = ft.FeatureImplementation.get_data(feature_execution_datasource_symbol=
                                                  self.feature_execution.featureexecutiondatasourcesymbol_set.all()[0])
        self.assertEqual(len(data.index), 1000)

        # Now add a feature calculation result for the 5 minutes (300 rows)
        time = datetime(2020, 1, 1, 0, 0, 0, 0, pytz.UTC)
        for i in range(0, 300):
            calc = random()
            time = time + timedelta(seconds=1)
            fexr = models.FeatureExecutionResult(feature_execution=self.feature_execution, time=time, result=calc)
            fexr.save()

        # Get the data again. This should include the 700 rows that dont have a feature calculation and an additional
        # 60 rows required for the calculation of the first one. 760 in total.
        data = ft.FeatureImplementation.get_data(feature_execution_datasource_symbol=
                                                 self.feature_execution.featureexecutiondatasourcesymbol_set.all()[0])
        self.assertEqual(len(data.index), 760)

        # Calculate the features for the remaining available data.
        time = datetime(2020, 1, 1, 0, 5, 0, 0, pytz.UTC)
        for i in range(0, 700):
            calc = random()
            time = time + timedelta(seconds=1)
            fexr = models.FeatureExecutionResult(feature_execution=self.feature_execution, time=time, result=calc)
            fexr.save()

        # Get the data again, there shouldn't be any as there are no more features left to calculate
        data = ft.FeatureImplementation.get_data(feature_execution_datasource_symbol=
                                                 self.feature_execution.featureexecutiondatasourcesymbol_set.all()[0])
        self.assertIsNone(data)




import logging
from datetime import datetime, timedelta
from random import random

import pytz
from django.test import TestCase

from plugin import models as pl_models
from pricedata import models as pd_models
from feature import models as ft_models

from movingaverage import MovingAverage


class TestMovingAverageFeature(TestCase):
    """
    Test case for testing the moving average feature
    """

    def setUp(self) -> None:
        """
        Create a datasource, symbol, candles and feature
        :return:
        """
        # Create a plugin and plugin class. We can use this for both the datasource and feature as it isn't part of what
        # we are testing
        plugin = pl_models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()
        self.plugin_class = pl_models.PluginClass(plugin=plugin, name="TestClassName", plugin_type="TestType")
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
        self.feature = ft_models.Feature(name="MovingAverage", pluginclass=self.plugin_class, calculation_period='1min',
                                         calculation_frequency='{"minute": "*"}')
        self.feature.save()
        self.feature_execution = ft_models.FeatureExecution(feature=self.feature)
        self.feature_execution.save()
        feature_execution_dss = ft_models.FeatureExecutionDataSourceSymbol(feature_execution=self.feature_execution,
                                                                           datasource_symbol=self.dss,
                                                                           candle_period='1S')
        feature_execution_dss.save()

    def test_execute(self):
        """
        Test execute implementation
        :return:
        """
        # Run execute, and count the results. We should have 1000 (same as the number of candles)
        ft_imp = MovingAverage(self.feature)
        ft_imp.execute(feature_execution=self.feature_execution)
        results = ft_models.FeatureExecutionResult.objects.all()
        self.assertEqual(len(results), 1000)

        # Iterate adding another candles, executing and counting results. We will do this three times, to demonstrate
        # whether test that duplicate entries are not being added (i.e. from results already calculated but used for
        # new calculations not being re-added)
        time = \
            ft_models.FeatureExecutionResult.objects.\
            filter(feature_execution=self.feature_execution).latest("time").time

        for i in range(0, 3):
            # Create 10 new candles
            for j in range(0, 10):

                price = random()
                time = time + timedelta(seconds=1)
                candle = pd_models.Candle(datasource_symbol=self.dss, time=time, period='1S', bid_open=price,
                                          bid_high=price, bid_low=price, bid_close=price, ask_open=price,
                                          ask_high=price,
                                          ask_low=price, ask_close=price, volume=i)
                candle.save()

            # Get the results
            ft_imp.execute(feature_execution=self.feature_execution)
            results = ft_models.FeatureExecutionResult.objects.all()

            # We should have 1000 + another 10 for every iteration of this loop
            self.assertEqual(len(results), 1000 + (i+1)*10)



import json
import logging

import pandas as pd
from django_celery_beat import models as cm

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from pricedata import models as pd_models


class Feature(models.Model):
    """
    Represents a feature to be calculated against pricedata candles
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The feature name
    name = models.CharField(max_length=30, unique=True)

    # The feature plugin class
    pluginclass = models.ForeignKey('plugin.PluginClass', on_delete=models.CASCADE,
                                    limit_choices_to={'plugin_type': 'FeatureImplementation'})

    # Calculation period. How far to look back to calculate (e.g. 30 day moving average will use 30D). A number
    # followed by any valid pandas timeseries offset alias.
    # https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases
    calculation_period = models.CharField(max_length=6)

    # Calculation frequency. How often to run the feature calculation. A string representation of a dict with crontab
    # parameters. e.g. '{"day_of_week": "mon-fri", "hour": 23, "minute": 0}'
    calculation_frequency = models.CharField(max_length=255)

    # Active.
    active = models.BooleanField(default=True)

    # The periodic task to calculate the feature
    task = models.OneToOneField(cm.PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)

    @property
    def task_name(self):
        """
        Returns the task name for executing this feature
        :return:
        """
        return f'feature.tasks.calculate_feature (id={self.id})'

    def setup_task(self):
        """
        Sets up the periodic task to calculate this feature.
        :return:
        """

        # Get the schedule from settings
        cron = json.loads(self.calculation_frequency)

        # Create the crontab schedule if it doesn't already exist
        schedule, created = cm.CrontabSchedule.objects.get_or_create(**cron)

        # Schedule the task
        self.task = cm.PeriodicTask.objects.create(
            name=self.task_name,
            task='calculate_feature',
            crontab=schedule,
            args=json.dumps([self.id])
            )

        self.save()

    def delete(self, *args, **kwargs):
        """
        Override delete to delete the feature execution calculation task when we delete the feature execution
        :param args:
        :param kwargs:
        :return:
        """
        if self.task is not None:
            self.task.delete()
        return super(self.__class__, self).delete(*args, **kwargs)

    def __repr__(self):
        return f"Feature(name={self.name}, pluginclass={self.pluginclass}, " \
               f"calculation_frequency={self.calculation_frequency}, calculation_period={self.calculation_period}, " \
               f"active={self.active}, task={self.task}"

    def __str__(self):
        return f"{self.name}"


class FeatureExecution(models.Model):
    """
    Represents a request to execute a feature calculation. One of these is required for every symbol or symbol set that
    the feature will run for.
    """
    # Logger
    __log = logging.getLogger(__name__)

    # The feature
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)

    # The name of this feature execution
    name = models.CharField(max_length=20, unique=True)

    # Active.
    active = models.BooleanField(default=True)

    def __repr__(self):
        return f"FeatureExecution(feature={self.feature}, name={self.name}, active={self.active}"

    def __str__(self):
        return f"{self.name}"


class FeatureExecutionDataSourceSymbol(models.Model):
    """
    A datasource symbol for the feature execution. A feature execution will include one or more symbols.
    * For single symbol calculations (e.g. 30 day moving average). The FeatureExecution will only include one symbol
    * For multi symbol calculations (e.g. correlation). The FeatureExecution will include two or more symbols.
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The feature execution
    feature_execution = models.ForeignKey(FeatureExecution, on_delete=models.CASCADE)

    # The datasource symbol
    datasource_symbol = models.ForeignKey(pd_models.DataSourceSymbol, on_delete=models.CASCADE)

    # Period for the candle data.
    candle_period = models.CharField(max_length=3, choices=pd_models.candle_periods)

    # Active.
    active = models.BooleanField(default=True)

    def __repr__(self):
        return f"FeatureExecutionSymbol(feature_execution={self.feature_execution}, " \
               f"datasource_symbol={self.datasource_symbol}, candle_period={self.candle_period}, active={self.active}"

    def __str__(self):
        return f"{self.feature_execution} Symbol: {self.datasource_symbol}."


class FeatureExecutionResult(models.Model):
    """
    The result of a single feature calculation for a FeatureExecution. There should be a result for every candle / set
    required for the feature execution, except for those that fall outside of the calculation period of the feature.
    i.e. for a 30 day moving average, the first 30 days of candle data will not have a feature calculation.
    """
    # The feature execution
    feature_execution = models.ForeignKey(FeatureExecution, on_delete=models.CASCADE)

    # The candle time that this result was calculated for
    time = models.DateTimeField()

    # The result
    result = models.DecimalField(max_digits=12, decimal_places=6)

    class Meta:
        unique_together = ('feature_execution', 'time',)

    def __repr__(self):
        return f"FeatureExecutionResult(feature_execution={self.feature_execution}, time={self.time}, " \
               f"result={self.result}"

    def __str__(self):
        return f"FeatureExecution: {self.feature_execution} time: {self.time} result: {self.result}."


@receiver(post_save, sender=Feature)
def save_feature_receiver(sender, instance, created, **kwargs):
    if created:
        instance.setup_task()
    else:
        if instance.task is not None:
            instance.task.enabled = instance.active
            instance.task.save()

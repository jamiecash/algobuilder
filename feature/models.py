import json
import logging

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
    name = models.CharField(max_length=20, unique=True)

    # The feature plugin class
    pluginclass = models.ForeignKey('plugin.PluginClass', on_delete=models.CASCADE,
                                    limit_choices_to={'plugin_type': 'FeatureImplementation'})

    # Active.
    active = models.BooleanField(default=True)

    def __repr__(self):
        return f"Feature(name={self.name}, pluginclass={self.pluginclass}, active={self.active}"

    def __str__(self):
        return f"{self.name}"


class FeatureExecution(models.Model):
    """
    Represents a request to execute a feature calculation for the specified datasource candleperiod. One of these is
    required for every symbol or symbol set that the feature will run for.
    """
    # Logger
    __log = logging.getLogger(__name__)

    # The feature
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)

    # Period for the candle data.
    candle_period = models.CharField(max_length=3, choices=pd_models.candle_periods)

    # Calculation period. How far to look back to calculate (e.g. 30 day moving average will use 30D). A number
    # followed by any valid pandas timeseries offset alias:
    # https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases
    calculation_period = models.CharField(max_length=6)

    # Active.
    active = models.BooleanField(default=True)

    # The periodic task to calculate the feature
    task = models.OneToOneField(cm.PeriodicTask, on_delete=models.CASCADE, null=True, blank=True)

    @property
    def symbols(self):
        """
        Returns the list of symbols for this feature execution.

        :return: Symbols
        """
        symbols = []

        feature_execution_symbols = self.featureexecutiondatasourcesymbol_set.all()
        for feature_execution_symbol in feature_execution_symbols:
            symbols.append(feature_execution_symbol.datasource_symbol.symbol)

        return symbols

    @property
    def task_name(self):
        """
        Returns the task name for executing this feature
        :return:
        """
        return f'Calculating {self.feature.name} feature execution id {self.id} for {self.candle_period}.'

    def setup_task(self):
        """
        Sets up the periodic task to calculate this feature execution.
        :return:
        """

        # Get the schedule from the period
        schedule = pd_models.schedules[self.candle_period]

        if isinstance(schedule, cm.IntervalSchedule):
            # Get or create the schedule
            schedule, created = cm.IntervalSchedule.objects.get_or_create(every=schedule.every, period=schedule.period)
            schedule.save()

            # Schedule the task
            self.task = cm.PeriodicTask.objects.create(
                name=self.task_name,
                task='calculate_feature',
                interval=schedule,
                args=json.dumps([self.id])
            )
        elif isinstance(schedule, cm.CrontabSchedule):
            # Get or create the schedule
            schedule, created = cm.CrontabSchedule.objects.get_or_create(hour=schedule.hour, minute=schedule.minute,
                                                                         day_of_week=schedule.day_of_week,
                                                                         day_of_month=schedule.day_of_month)
            schedule.save()

            # Schedule the task
            self.task = cm.PeriodicTask.objects.create(
                name=self.task_name,
                task='calculate_feature',
                crontab=schedule,
                args=json.dumps([self.id])
            )
        else:
            self.__log.warning(f"Cannot schedule feature. Unsupported schedule. Type={type(schedule)}.")
            # TODO Add support for solar and clocked schedules

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
        return f"FeatureExecution(feature={self.feature}, candle_period={self.candle_period}, " \
               f"calculation_period={self.calculation_period}, active={self.active}"

    def __str__(self):
        return f"Feature: {self.feature} candle_period: {self.candle_period} " \
               f"calculation_period: {self.calculation_period}."


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

    # Active.
    active = models.BooleanField(default=True)

    def __repr__(self):
        return f"FeatureExecutionSymbol(feature_execution={self.feature_execution}, " \
               f"datasource_symbol={self.datasource_symbol}, active={self.active}"

    def __str__(self):
        return f"FeatureExecution: {self.feature_execution} Symbol: {self.datasource_symbol}."


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


@receiver(post_save, sender=FeatureExecution)
def save_feature_execution_receiver(sender, instance, created, **kwargs):
    if created:
        instance.setup_task()
    else:
        if instance.task is not None:
            instance.task.enabled = instance.active
            instance.task.save()

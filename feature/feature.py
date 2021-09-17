import abc
import logging
import pandas as pd
from django.db import connection

from datetime import datetime
from pricedata import models as pd_models
from feature import models as ft_models


class FeatureInstanceNotImplementedError(Exception):
    """
    An exception that can be raised by instance if specified feature is not implemented.
    """
    pass


class FeatureImplementation:
    """
    The interface for applications features
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The model class containing the properties for the feature. Protected to enable implementations of this class
    # only to access.
    _feature = None

    def __init__(self, feature: ft_models.Feature) -> None:
        """
        Construct the feature implementation and stores its model
        :param feature: The Feature model instance.
        """
        self._feature = feature

    @staticmethod
    def instance(name: str):
        """
        Get the Feature instance specified by the name.
        :param name:
        :return:
        """

        features = ft_models.Feature.objects.filter(name=name)

        if len(features) != 0:
            f = features[0]

            # Get plugin class
            clazz = f.pluginclass.plugin_class
        else:
            raise FeatureInstanceNotImplementedError(f'FeatureImplementation instance cannot be created for '
                                                     f'feature {name}. Feature could not be found.')

        return clazz(f)

    @staticmethod
    def all_instances():
        """
        Returns a list of all Features
        :return:
        """
        all_feature_models = ft_models.Feature.objects.all()

        all_feature_implementations = []
        for feature_model in all_feature_models:
            all_feature_implementations.append(FeatureImplementation.instance(feature_model))

        return all_feature_implementations

    @staticmethod
    def get_data_from_date(feature_execution: ft_models.FeatureExecution) -> datetime:
        """
        Gets the from date for required candle data to calculate this features for the supplied feature_execution.

        from_date will be the next calculation date - the calculation period

        If we have previously calculated a feature for this feature execution, then the next calculation date will be
        the earliest date where we have candle data available for all required datasource symbols, that we have not
        already calculated this feature for.

        If we have not previously calculated a feature for this feature execution, then the next calculation date will
        be the earliest date where we have candle data available for all required datasource symbols.

        @:param feature_execution: The feature execution to get the data from date for

        :return: A datetime specifying the from date for the candle data required to calculate this feature
        """

        # SQL to get the next calculation date based on the candles available for the datasource symbols required for
        # the feature execution
        sql = \
            """
            SELECT min(times.time)
            FROM
                (
                    SELECT cnd.time as time
                    FROM pricedata_candle cnd INNER JOIN
                        (
                            SELECT 	datasource_symbol_id,
                                    feds.candle_period
                            FROM 	feature_featureexecutiondatasourcesymbol feds INNER JOIN
                                        pricedata_datasourcesymbol dss ON
                                            feds.datasource_symbol_id = dss.id
                            WHERE 	feds.feature_execution_id = %s
                        ) AS ft_dss ON
                        cnd.datasource_symbol_id = ft_dss.datasource_symbol_id AND
                        cnd.period = ft_dss.candle_period
                    GROUP BY cnd.time
                    HAVING COUNT(cnd.time) = 
                        (
                            SELECT COUNT(datasource_symbol_id)
                            FROM feature_featureexecutiondatasourcesymbol feds
                                INNER JOIN pricedata_datasourcesymbol dss ON feds.datasource_symbol_id = dss.id
                            WHERE feds.feature_execution_id = %s
                        )
                ) as times
            """

        # If we have calculated this feature before, get the last calculation time and append to sql query
        last_calc_exists = \
            ft_models.FeatureExecutionResult.objects.filter(feature_execution=feature_execution).last() is not None
        if last_calc_exists:
            last_calc =\
                ft_models.FeatureExecutionResult.objects.filter(feature_execution=feature_execution).latest("time")
            last_calc_time = last_calc.time
            sql += f" WHERE times.time > '{last_calc_time}'"

        # Run the SQL
        with connection.cursor() as cursor:
            cursor.execute(sql, [feature_execution.id, feature_execution.id])
            row = cursor.fetchone()

        next_calc_time = row[0]

        # If we have a next_calc time then from date for candle data is next candle - calculation period.
        # No need to - calculation period for the first time that we calculate the feature as we are already getting the
        # first available date.
        # If we don't have a next_calc_time, then from_date will be None
        from_date = None
        if next_calc_time is not None:
            cp_td = pd.to_timedelta(feature_execution.feature.calculation_period)
            from_date = next_calc_time - cp_td if last_calc_exists else next_calc_time

        return from_date

    @staticmethod
    def get_data(feature_execution_datasource_symbol: ft_models.FeatureExecutionDataSourceSymbol) -> pd.DataFrame:
        """
        Gets the data for the specified feature execution datasource symbol required to calculate the feature.
        :param feature_execution_datasource_symbol:
        :return: Dataframe containing candle data for the specified feature_execution_datasource_symbol. Will return
            None there are no features left to calculate.
        """

        # Get the from date
        from_date = FeatureImplementation.get_data_from_date(feature_execution_datasource_symbol.feature_execution)

        dataframe = None
        if from_date is not None:
            # Get the data. QuerySet to get the candles and feature results, then convert to dataframe with outer join
            # on time so that we can identify those already calculated so that we don't update again. Sort and index on
            # time.
            candles = pd_models.Candle.\
                objects.filter(datasource_symbol=feature_execution_datasource_symbol.datasource_symbol,
                               time__gte=from_date).all()

            results = ft_models.FeatureExecutionResult.objects.\
                filter(feature_execution=feature_execution_datasource_symbol.feature_execution,
                       time__gte=from_date).all()

            df_candles = pd.DataFrame(list(candles.values()))
            df_results = pd.DataFrame(list(results.values()))

            # If we have results, join them otherwise just return the candles with empty results columns
            if len(df_results.index) > 0 and len(df_candles.index) > 0:
                df_candles = df_candles.set_index('time')
                df_results = df_results.set_index('time')
                dataframe = pd.concat([df_candles, df_results], axis=1, join="outer").sort_index()
            elif len(df_candles.index) > 0:
                dataframe = df_candles.set_index('time').sort_index()
                dataframe['result'] = None
                dataframe['feature_execution_id'] = None

        # Return the dataframe
        return dataframe

    @abc.abstractmethod
    def execute(self, feature_execution):
        """
        Executes the feature calculation for a single feature execution

        :param feature_execution: The feature execution containing the datasource_candleperiod, calculation_period and
            symbols for the calculation
        """
        raise NotImplementedError

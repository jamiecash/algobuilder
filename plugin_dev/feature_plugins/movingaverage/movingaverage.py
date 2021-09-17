import logging

from algobuilder.utils import DatabaseUtility
from feature import feature as ft
from feature import models


class MovingAverage(ft.FeatureImplementation):
    """
    Calculates a moving average
    """

    # Logger
    __log = logging.getLogger(__name__)

    def execute(self, feature_execution):
        """
        Executes the feature calculation for a single execution
        :param feature_execution:
        :return:
        """
        # Get the symbols. There should only be 1
        assert len(feature_execution.featureexecutiondatasourcesymbol_set.all()) == 1
        feds = feature_execution.featureexecutiondatasourcesymbol_set.all()[0]

        self.__log.debug(f"Calculating moving average for {feature_execution}. FeatureExecutionDataSourceSymbol={feds}")

        # Get the data. Candles that don't have a feature calculated and those that do but are required for teh first
        # calculation.
        data = ft.FeatureImplementation.get_data(feds)

        # If get_data returned None, then we don't have any features to calculate. Otherwise calculate the moving
        # average from the data.
        if data is not None:
            # Calculate the moving average
            data['moving_average'] = data['bid_close'].rolling(feature_execution.feature.calculation_period).mean()

            # Remove the rows that already had a result and were only used to calculate the first results.
            data = data[data['result'].isna()]

            # Reshape the dataframe for upload into the feature_execution_result table. This will require candle_id,
            # feature_execution_id and result
            data = data.reset_index()
            data['feature_execution_id'] = feature_execution.id
            data['result'] = data['moving_average']
            data = data.drop(labels=data.columns.difference(['time', 'feature_execution_id', 'result']), axis=1)

            # Save the calculations
            DatabaseUtility.bulk_insert_or_update(data=data,
                                                  table=models.FeatureExecutionResult.objects.model._meta.db_table,
                                                  batch_size=1000)

        else:
            self.__log.debug(f"Feature calculations up to date. No new features calculated for "
                             f"{feds.datasource_symbol.symbol.name}.")

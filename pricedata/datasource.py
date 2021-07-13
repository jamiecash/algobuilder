"""
The DataSourceImplementation interface. Subclasses will be used to connect to price data sources.
"""

import abc
import importlib
import logging
import pandas as pd
import subprocess
import sys
from datetime import datetime
from typing import List, Dict

from pricedata import models


class PeriodNotImplementedError(Exception):
    """
    An exception that can be raised by sub classes get_prices method for periods that are not implemented.
    """
    pass


class DataSourceInstanceNotImplementedError(Exception):
    """
    An exception that can be raised by instance if specified datasource is not implemented.
    """
    pass


class DataSourceImplementation:
    """
    The interface for applications datasources
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The model class containing the properties for the data source. Protected to enable implementations of this class
    # only to access.
    _data_source_model = None

    # The get_prices implementation should return a pandas dataframe with the following columns
    _prices_columns = ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close', 'ask_open', 'ask_high',
                       'ask_low', 'ask_close', 'volume']

    def __init__(self, data_source_model: models.DataSource) -> None:
        """
        Construct the datasource implementation and stores its model
        :param data_source_model: The DataSource model instance containing the details required to create and connect to
        this datasource.
        """
        self._data_source_model = data_source_model

    @staticmethod
    def instance(name: str):
        """
        Get the DataSource instance specified by the name.
        :param name:
        :return:
        """

        data_source_model = models.DataSource.objects.filter(name=name)[0]

        if data_source_model.module.name != '' and data_source_model.class_name != '':
            # Get module and class name
            module_name = data_source_model.module.name
            class_name = data_source_model.class_name

            # Remove .py and replace / with .
            module_name = module_name.replace('/', '.')
            module_name = module_name.replace('.py', '')

            # Load module and initialise class
            try:
                module = importlib.import_module(module_name)
                clazz = getattr(module, class_name)
            except NameError as ex:
                raise DataSourceInstanceNotImplementedError(
                    f'DataSource instance cannot be created for datasource {name}.', ex)
        else:
            raise DataSourceInstanceNotImplementedError(f'DataSource instance cannot be created for datasource {name}. '
                                                        f'Either module or classname has not been provided. '
                                                        f'module={data_source_model.module.name}, '
                                                        f'classname={data_source_model.class_name}.')

        return clazz(data_source_model)

    @staticmethod
    def all_instances():
        """
        Retruns a list of all DataSources
        :return:
        """
        all_datasource_models = models.DataSource.objects.all()

        all_datasource_implementations = []
        for datasource_model in all_datasource_models:
            all_datasource_implementations.append(DataSourceImplementation.instance(datasource_model))

        return all_datasource_implementations

    @staticmethod
    def configure(datasource: models.DataSource):
        """
        Configure this datasource for its first use. Installs dependencies and copies symbols over to database.
        :return:
        """

        # Install libraries in requirements file. This must be done prior to instance being created due to dependencies
        if datasource.requirements_file.name != '':
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r',
                                       f'{datasource.requirements_file.name}'])
            except subprocess.CalledProcessError as ex:
                DataSourceImplementation.__log.warning(f"Requirements for DataSource {datasource.name} could not be "
                                                       f"installed.",  ex)

        # Get symbols from instance
        instance = DataSourceImplementation.instance(datasource.name)
        ds_symbols = instance.get_symbols()

        # Update the database. We will update in bulk due to potential volume of symbols from datasource
        new_symbols = []
        new_ds_symbols = []
        for ds_symbol in ds_symbols:
            # Get symbol if it already exists, otherwise create it
            symbols = models.Symbol.objects.filter(name=ds_symbol['symbol_name'])
            if len(symbols) > 0:
                symbol = symbols[0]
            else:
                # Add it.
                symbol = models.Symbol(name=ds_symbol['symbol_name'], instrument_type=ds_symbol['instrument_type'])
                new_symbols.append(symbol)

            # Create a DataSourceSymbol if it doesnt already exist
            ds_symbols = models.DataSourceSymbol.objects.filter(datasource=datasource, symbol=symbol)

            if len(ds_symbols) == 0:
                ds_symbol = models.DataSourceSymbol(datasource=datasource, symbol=symbol)
                new_ds_symbols.append(ds_symbol)

        # Bulk create
        DataSourceImplementation.__log.debug(f"Bulk creating {len(new_symbols)} symbols and {len(new_ds_symbols)} "
                                             f"datasource symbol records for datasource {datasource}.")
        models.Symbol.objects.bulk_create(new_symbols)
        models.DataSourceSymbol.objects.bulk_create(new_ds_symbols)

    @abc.abstractmethod
    def get_symbols(self) -> List[Dict[str, str]]:
        """
        Get symbols from datasource

        :return: list of dictionaries containing symbol_name and instrument_type
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_prices(self, symbol: str, from_date: datetime, to_date: datetime, period: str) -> pd.DataFrame:
        """
        Gets OHLC price data for the specified symbol.
        :param symbol: The name of the symbol to get the price data for.
        :param from_date: Date from when to retrieve data
        :param to_date: Date to receive data up to
        :param period: The period for the candes. Possible values are defined in models.candle_periods.

        :return: Price data for symbol as pandas dataframe containing the following columns:
            ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close',
            'ask_open', 'ask_high', 'ask_low', 'ask_close', 'volume']
        """
        raise NotImplementedError



"""
The DataSource interface
"""

import abc
import importlib
import logging
import subprocess
import sys

from pricedata.models import DataSource, DataSourceSymbol, Symbol


class DataSourceImplementation:
    """
    The interface for applications datasources
    """

    # Logger
    __log = logging.getLogger(__name__)

    _data_source_model = None  # Protected. Available to implementations of this class only.

    def __init__(self, data_source_model: DataSource) -> None:
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

        data_source_model = DataSource.objects.filter(name=name)[0]

        # Get module and class name
        module_name = data_source_model.module.name
        class_name = data_source_model.class_name

        # Remove .py and replace / with .
        module_name = module_name.replace('/', '.')
        module_name = module_name.replace('.py', '')

        # Load module and initialise class
        module = importlib.import_module(module_name)
        clazz = getattr(module, class_name)

        return clazz(data_source_model)

    @staticmethod
    def all_instances():
        """
        Retruns a list of all DataSources
        :return:
        """
        all_datasource_models = DataSource.objects.all()

        all_datasource_implementations = []
        for datasource_model in all_datasource_models:
            all_datasource_implementations.append(DataSourceImplementation.instance(datasource_model))

        return all_datasource_implementations

    @staticmethod
    def configure(datasource):
        """
        Configure this datasource for its first use. Installs dependencies and copies symbols over to database.
        :return:
        """

        # Install libraries in requirements file. This must be done prior to instance being created due to dependencies
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r',
                                   f'{datasource.requirements_file.name}'])
        except subprocess.CalledProcessError as ex:
            DataSourceImplementation.__log.warning(f"Requirements for DataSource {datasource.name} could not be "
                                                   f"installed.",  ex)

        # Get symbols from instance
        instance = DataSourceImplementation.instance(datasource.name)
        symbol_names = instance.get_symbols()

        # Update the database
        for symbol_name in symbol_names:
            # Get symbol if it already exists, otherwise create it
            symbols = Symbol.objects.filter(name=symbol_name)
            if len(symbols) > 0:
                symbol = symbols[0]
            else:
                # Add it.
                symbol = Symbol(name=symbol_name)
                DataSourceImplementation.__log.debug(f"Creating new symbol {symbol} in database.")
                symbol.save()

            # Create a DataSourceSymbol if it doesnt already exist
            ds_symbols = DataSourceSymbol.objects.filter(datasource=datasource, symbol=symbol)

            if len(ds_symbols) == 0:
                ds_symbol = DataSourceSymbol(datasource=datasource, symbol=symbol)
                ds_symbol.save()

    @abc.abstractmethod
    def get_symbols(self):
        """
        Returns list of symbol names from data source
        :return:
        """
        raise NotImplementedError


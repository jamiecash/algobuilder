import logging

import pandas as pd
from background_task import background
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone
from django.db import connection

from pricedata import datasource
from pricedata.models import Candle


class DataRetriever:
    """
    A class containing the method to retrieve symbol and price data from the data source and populate the application
    """

    # Logger
    __log = logging.getLogger(__name__)

    # Define number of days of data to retrieve on each run for each time period
    period_batch_days = candle_periods = {'1S': 1/24, '5S': 1/24*5, '10S': 1/24*10, '15S': 1/24*15, '30S': 1, '1M': 1,
                                          '5M': 5, '10M': 10, '15M': 15, '30M': 30, '1H': 60, '3H': 60, '6H': 60,
                                          '12H': 60, '1D': 120, '1W': 120, '1MO': 120}

    @staticmethod
    @background(schedule=0, queue='price-data')
    def retrieve_prices(datasource_candleperiod_id: int) -> None:
        # Call un-decorated method. Enables unit-testing of functional code outside of tasks framework
        DataRetriever.retrieve_prices_impl(datasource_candleperiod_id)

    @staticmethod
    @background(schedule=0, queue='symbol-data')
    def retrieve_symbols(datasource_id):
        # Call un-decorated method. Enables unit-testing of functional code outside of tasks framework
        DataRetriever.retrieve_symbols_impl(datasource_id)

    @staticmethod
    def retrieve_prices_impl(datasource_candleperiod_id: int):
        """
        Retrieves prices for datasource candle period from datasource and populates in application database
        :param datasource_candleperiod_id:
        :return:
        """
        from pricedata import models  # Imported when needed, due to circular dependency

        # Logger
        log = logging.getLogger(__name__)

        # Get the datasource candleperiod mapping class from its id
        ds_pc = models.DataSourceCandlePeriod.objects.get(id=datasource_candleperiod_id)

        # Only continue if active
        if ds_pc.active:
            # Get candles
            log.debug(f"Getting price data for {ds_pc.datasource.name} for period {ds_pc.period}.")

            # Get datasource instance to retrieve data from
            ds_instance = datasource.DataSourceImplementation.instance(ds_pc.datasource.name)

            # Get the symbols where we will retrieving price data for
            datasource_symbols = models.DataSourceSymbol.objects.filter(datasource=ds_pc.datasource,
                                                                        retrieve_price_data=True)

            # Iterate symbols, retrieving price data
            for datasource_symbol in datasource_symbols:
                symbol = datasource_symbol.symbol.name

                # Get last candle for period / symbol / datasource saved. If there is one then our from_date will be the
                # candle time + 1ms. If there isn't one, our from_date will be the DataSourcePeriodCandles start_from
                # date.
                from_date = ds_pc.start_from
                last_candle_time = models.Candle.objects.filter(datasource_symbol=datasource_symbol,
                                                                period=ds_pc.period).aggregate(Max('time'))['time__max']

                if last_candle_time is not None:
                    from_date = last_candle_time + timedelta(milliseconds=1)

                # To date is now.
                to_date = timezone.now()

                # Get the data
                try:
                    data = ds_instance.get_prices(symbol, from_date, to_date, ds_pc.period)
                    log.debug(f"{len(data.index)} {ds_pc.period} candles retrieved from {ds_pc.datasource.name} for "
                              f"{symbol} to {to_date}.")

                    # Prepare the dataframe for bulk upsert by adding the datasource symbol.
                    data['datasource_symbol_id'] = datasource_symbol.id

                    # Update or insert. We need he data, the table name and the list of unique fields.
                    unique_fields = ['datasource_symbol_id', 'time', 'period']
                    table = Candle.objects.model._meta.db_table
                    DataRetriever.__bulk_insert_or_update(data=data, table=table, unique_fields=unique_fields)
                except datasource.DataNotAvailableException as ex:
                    DataRetriever.__log.warning(ex)
        else:
            # Inactive
            log.debug(f"Task running for DataSourceCandlePeriod {ds_pc}.")

    @staticmethod
    def retrieve_symbols_impl(datasource_id):
        """
        Retrieves symbols for datasource and populates in application database
        :param datasource_id:
        :return:
        """
        from pricedata import models  # Imported when needed, due to circular dependency

        # Get the datasource candleperiod mapping class from its id
        ds = models.DataSource.objects.get(id=datasource_id)

        # Get an instance of the datasource implementation to retrieve symbols from
        instance = datasource.DataSourceImplementation.instance(ds.name)

        # Get symbols from instance
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
            ds_symbols = models.DataSourceSymbol.objects.filter(datasource=ds, symbol=symbol)

            if len(ds_symbols) == 0:
                ds_symbol = models.DataSourceSymbol(datasource=ds, symbol=symbol)
                new_ds_symbols.append(ds_symbol)

        # Bulk create
        DataRetriever.__log.debug(f"Bulk creating {len(new_symbols)} symbols and {len(new_ds_symbols)} datasource "
                                  f"symbol records for datasource {datasource}.")

        models.Symbol.objects.bulk_create(new_symbols)
        models.DataSourceSymbol.objects.bulk_create(new_ds_symbols)

    @staticmethod
    def __bulk_insert_or_update(data: pd.DataFrame, table: str, unique_fields):
        """
        Bulk insert or update (upsert) of price data. If pk already exists, then update else insert

        :param data: The pandas dataframe to insert / update to db. The columns in the dataframe must match the table
            columns.
        :param table: The name of the table to update
        :param unique_fields: Fields that will raise the unique key constraint on insert
        :return:
        """

        # Get create fields from dataframe and the update fields as the create fields - unique fields
        create_fields = data.columns
        update_fields = set(create_fields) - set(unique_fields)

        # Get teh values from the data
        values = [tuple(x) for x in data.to_numpy()]

        cursor = connection.cursor()

        # Mogrify values to bind into sql.
        mogvals = [cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", val).decode('utf8') for val in values]

        # Build list of x = excluded.x columns for SET part of sql
        on_duplicates = []
        for field in update_fields:
            on_duplicates.append(field + "=excluded." + field)

        # SQL
        sql = f"INSERT INTO {table} ({','.join(list(create_fields))}) VALUES {','.join(mogvals)} " \
              f"ON CONFLICT ({','.join(list(unique_fields))}) DO UPDATE SET {','.join(on_duplicates)}"

        cursor.execute(sql)
        cursor.close()

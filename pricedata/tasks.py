import logging

from background_task import background
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone

from pricedata import datasource


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
                # date. We will need the id of the last candle for update.
                from_date = ds_pc.start_from
                last_candle_time = models.Candle.objects.filter(datasource_symbol=datasource_symbol, period=ds_pc.period).\
                    aggregate(Max('time'))['time__max']
                last_candle_id = None

                if last_candle_time is not None:
                    from_date = last_candle_time + timedelta(milliseconds=1)
                    last_candles = models.Candle.objects.filter(datasource_symbol=datasource_symbol,
                                                                period=ds_pc.period, time=last_candle_time)

                    # There should be exactly 1. Get the id
                    assert len(last_candles) == 1
                    last_candle_id = last_candles[0].id

                # To date is now.
                to_date = timezone.now()

                # Get the data
                data = ds_instance.get_prices(symbol, from_date, to_date, ds_pc.period)
                log.debug(f"{len(data.index)} {ds_pc.period} candles retrieved from {ds_pc.datasource.name} for "
                          f"{symbol} to {to_date}.")

                # Prepare the dataframe for bulk update by adding the datasource symbol.
                data['datasource_symbol'] = datasource_symbol

                # We may have a row for the last candle time if our datasource resampled. This should be updated
                # rather than created. Update row needs an id. There should not be more than one.
                update_rows = data[data['time'] == last_candle_time]
                if len(update_rows.index) == 1:
                    update_candle = models.Candle.objects.get(id=last_candle_id)
                    update_candle.bid_open = update_rows['bid_open'].iloc[0]
                    update_candle.bid_high = update_rows['bid_high'].iloc[0]
                    update_candle.bid_low = update_rows['bid_low'].iloc[0]
                    update_candle.bid_close = update_rows['bid_close'].iloc[0]
                    update_candle.ask_open = update_rows['ask_open'].iloc[0]
                    update_candle.ask_high = update_rows['ask_high'].iloc[0]
                    update_candle.ask_low = update_rows['ask_low'].iloc[0]
                    update_candle.ask_close = update_rows['ask_close'].iloc[0]
                    update_candle.volume = update_rows['volume'].iloc[0]
                    update_candle.save()

                # Split out the create rows and bulk create
                create_rows = data[data['time'] != last_candle_time]
                models.Candle.objects.bulk_create(
                    models.Candle(**vals) for vals in create_rows.to_dict('records')
                )
        else:
            # Inactive
            log.debug(f"Task running for inactive DataSourceCandlePeriod {ds_pc}.")

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

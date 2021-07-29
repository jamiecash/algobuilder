import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

import MetaTrader5

from pricedata.datasource import DataSourceImplementation, DataNotAvailableException


class MT5DataSource(DataSourceImplementation):
    """
    MetaTrader 5 DataSource
    """

    def __init__(self, data_source_model):
        # Super
        DataSourceImplementation.__init__(self, data_source_model=data_source_model)

        # Connect to MetaTrader5. Opens if not already open.

        # Logger
        self.__log = logging.getLogger(__name__)

        # Open MT5 and log error if it could not open
        if not MetaTrader5.initialize():
            self.__log.error("initialize() failed")
            MetaTrader5.shutdown()

        # Print connection status
        self.__log.debug(MetaTrader5.terminal_info())

        # Print data on MetaTrader 5 version
        self.__log.debug(MetaTrader5.version())

    def __del__(self):
        # shut down connection to the MetaTrader 5 terminal
        MetaTrader5.shutdown()

    def get_symbols(self) -> List[Dict[str, str]]:
        """
        Get symbols from MetaTrader5

        :return: list of dictionaries containing symbol_name and instrument_type
        """

        all_symbols = MetaTrader5.symbols_get()

        # Are we returning MarketWatch symbols only
        market_watch_only = self._data_source_model.get_connection_param('market_watch_only')

        # We are returning the symbol names and instrument types
        symbols = []

        # Iterate all symbols, and populate symbol names, taking into account visible flag if we are returning market
        # watch symbols only.
        for symbol in all_symbols:
            if market_watch_only is False or (market_watch_only is True and symbol.visible):
                instrument_type = None
                if symbol.path.startswith('CFD'):
                    instrument_type = 'CFD'
                elif symbol.path.startswith('Forex'):
                    instrument_type = 'FOREX'

                symbols.append({'symbol_name': symbol.name, 'instrument_type': instrument_type})

        # Log symbol counts
        total_symbols = MetaTrader5.symbols_total()
        num_selected_symbols = len(symbols)
        self.__log.debug(f"{num_selected_symbols} of {total_symbols} returned. market_watch_only={market_watch_only}.")

        return symbols

    def get_prices(self, symbol: str, from_date: datetime, to_date: datetime, period: str) -> pd.DataFrame:
        """
        Gets OHLC price data for the specified symbol from MT5.
        :param symbol: The name of the symbol to get the price data for.
        :param from_date: Date from when to retrieve data
        :param to_date: Date to receive data up to
        :param period: The period for the candes. Possible values are defined in models.candle_periods:

        :return: Price data for symbol as pandas dataframe containing the following columns:
            ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close',
            'ask_open', 'ask_high', 'ask_low', 'ask_close', 'volume']
        """

        prices_dataframe = None

        # Mappings between defined periods and MT5 timeframes
        period_mapping = {
            '1S': None, '5S': None, '10S': None, '15S': None, '30S': None, '1M': MetaTrader5.TIMEFRAME_M1,
            '5M': MetaTrader5.TIMEFRAME_M5, '10M': MetaTrader5.TIMEFRAME_M10, '15M': MetaTrader5.TIMEFRAME_M15,
            '30M': MetaTrader5.TIMEFRAME_M30, '1H': MetaTrader5.TIMEFRAME_H1, '3H': MetaTrader5.TIMEFRAME_H3,
            '6H': MetaTrader5.TIMEFRAME_H6, '12H': MetaTrader5.TIMEFRAME_H12, '1D': MetaTrader5.TIMEFRAME_D1,
            '1W': MetaTrader5.TIMEFRAME_W1, '1MO': MetaTrader5.TIMEFRAME_MN1}

        # Get the MT5 timeframe from the supplied period
        timeframe = period_mapping[period]

        # If we have an equivalent timeframe in MT5, get candles, otherwise get ticks and resample
        if timeframe is not None:
            # Get prices from MT5
            prices = self.__get_rates(symbol, from_date, to_date, period, timeframe)
            self.__log.debug(f"{len(prices)} prices retrieved for {symbol}.")

            # Create dataframe from data and convert time in seconds to datetime format
            prices_dataframe = \
                pd.DataFrame(columns=self._prices_columns,
                             data={'time': prices['time'], 'period': period, 'bid_open': prices['open'],
                                   'bid_high': prices['high'], 'bid_low': prices['low'],
                                   'bid_close': prices['close'],
                                   'ask_open': prices['open'] + prices['spread'] / 10000,
                                   'ask_high': prices['high'] + prices['spread'] / 10000,
                                   'ask_low': prices['low'] + prices['spread'] / 10000,
                                   'ask_close': prices['close'] + prices['spread'] / 10000,
                                   'volume': prices['tick_volume']})

            prices_dataframe['time'] = pd.to_datetime(prices_dataframe['time'], unit='s')
        else:
            # Get ticks from MT5
            ticks = self.__get_ticks(symbol, from_date, to_date, period)
            self.__log.debug(f"{len(ticks)} ticks retrieved for {symbol}.")

            try:
                # Create dataframe from data and convert time in seconds to datetime format
                ticks_dataframe = pd.DataFrame(ticks)
                ticks_dataframe['time'] = pd.to_datetime(ticks_dataframe['time'], unit='s')

                # Set the index, resample bid and ask columns, merge, then reset index
                ticks_dataframe = ticks_dataframe.set_index('time')
                ohlc_calcs = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'count'}
                bid_candles = ticks_dataframe['bid'].resample(period).agg(ohlc_calcs)
                ask_candles = ticks_dataframe['ask'].resample(period).agg(ohlc_calcs)
                prices_dataframe = pd.concat([bid_candles, ask_candles], axis=1)
                prices_dataframe.reset_index(inplace=True)

                # We should now have time and (open, high, low, close, volume) * 2, one for bid and one for ask.
                # Add period, rename the columns, then delete the first volume column.
                prices_dataframe.insert(1, 'period', period)
                prices_dataframe.columns = ['time', 'period', 'bid_open', 'bid_high', 'bid_low', 'bid_close',
                                            'bid_volume', 'ask_open', 'ask_high', 'ask_low', 'ask_close', 'volume']
                prices_dataframe.drop('bid_volume', axis=1, inplace=True)  # First volume column

                # Remove n/a
                prices_dataframe = prices_dataframe.dropna()

            except RecursionError as ex:
                self.__log.warning("Error converting ticks to dataframe and resampling.", ex)

        # If the dataframe is None, create an empty one
        if prices_dataframe is None:
            prices_dataframe = pd.DataFrame(columns=self._prices_columns)

        # Make time timezone aware. Times returned from MT5 are in UTC
        if not prices_dataframe.empty:
            prices_dataframe['time'] = prices_dataframe['time'].dt.tz_localize('UTC')

        return prices_dataframe

    @staticmethod
    def __get_batches(from_date: datetime, to_date: datetime, period: str) -> List[Tuple[datetime, datetime]]:
        """
        Gets a list of from and to dates for batching of requests.
        :param from_date: The from date
        :param to_date: The to date
        :param period: The period for the candles. Lower periods require smaller batch sizes.
        :return: list of from date and to date pairs covering range of from and to dates, split into batches.
        """
        # Define number of days of data to retrieve on each run for each time period
        period_batch_days = {'1S': 1 / 24, '5S': 1 / 24 * 5, '10S': 1 / 24 * 10, '15S': 1 / 24 * 15, '30S': 1, '1M': 1,
                             '5M': 5, '10M': 10, '15M': 15, '30M': 30, '1H': 60, '3H': 60, '6H': 60, '12H': 60,
                             '1D': 120, '1W': 120, '1MO': 120}

        batches = []
        last_batch_to = from_date  # for first run.
        while last_batch_to < to_date:
            # The first batch starts from from date. Subsequent batches start from 1ms past the last batches to date.
            # Batches end earliest of the end date for the batch size or the to date.
            batch_from = from_date if last_batch_to is None else (last_batch_to + timedelta(milliseconds=1))
            batch_to = min(batch_from + timedelta(days=period_batch_days[period]), to_date)
            batches.append((batch_from, batch_to))
            last_batch_to = batch_to

        return batches

    def __get_rates(self, symbol: str, from_date: datetime, to_date: datetime, period: str,
                    timeframe: int) -> pd.DataFrame:
        """
        Gets rates from MT5, handling batching
        :param symbol: The symbol to retrieve price data for
        :param from_date: The date to retrieve the price data from
        :param to_date: The date to retrieve the price data to
        :param period: The period to retrieve. Used to calculate batch size
        :param timeframe: The timeframe for the candles to retrieve
        :return: dataframe
        """
        batches = MT5DataSource.__get_batches(from_date, to_date, period)

        # The dataframe to contain the full dataset
        data = None

        for batch in batches:
            # Get the data
            prices = MetaTrader5.copy_rates_range(symbol, timeframe, batch[0], batch[1])
            if prices is None:
                error = MetaTrader5.last_error()
                raise DataNotAvailableException(datasource=self._data_source_model.name, symbol=symbol, period=period,
                                                from_date=from_date, to_date=to_date, error_code=error[0],
                                                error_message=error[1])
            else:
                # Create or append to dataframe
                data = pd.DataFrame(prices) if data is None else data.append(pd.DataFrame(prices))

        # Remove any duplicates. Datasource can return refreshed candle if end time of previous batch and start time of
        # current batch is within the same candle period.
        data = data.drop_duplicates(subset=['time'], keep='last')

        return data

    def __get_ticks(self, symbol: str, from_date: datetime, to_date: datetime, period: str) -> pd.DataFrame:
        """
        Gets ticks from MT5, handling batching
        :param symbol: The symbol to retrieve tick data for
        :param from_date: The date to retrieve the price data from
        :param to_date: The date to retrieve the price data to
        :param period: The period to retrieve. Used to calculate batch size
        :return: dataframe
        """
        batches = MT5DataSource.__get_batches(from_date, to_date, period)

        # The dataframe to contain the full dataset
        data = None

        for batch in batches:
            # Get the data
            ticks = MetaTrader5.copy_ticks_range(symbol, batch[0], batch[1], MetaTrader5.COPY_TICKS_ALL)
            if ticks is None:
                error = MetaTrader5.last_error()
                raise DataNotAvailableException(datasource=self._data_source_model.name, symbol=symbol, period=period,
                                                from_date=from_date, to_date=to_date, error_code=error[0],
                                                error_message=error[1])
            else:
                # Create or append to dataframe
                data = pd.DataFrame(ticks) if data is None else data.append(pd.DataFrame(ticks))

        return data

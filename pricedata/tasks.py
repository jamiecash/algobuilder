import json
import logging
import pandas as pd
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone
from django.db import connection

from pricedata import datasource
from algobuilder.utils import DatabaseUtility


@shared_task(name='retrieve_prices', queue='pricedata')
def retrieve_prices(datasource_candleperiod_id: int):
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
                # Get the prices
                data = ds_instance.get_prices(symbol, from_date, to_date, ds_pc.period,
                                              datasource_symbol.symbol_info_dict)
                log.debug(f"{len(data.index)} {ds_pc.period} candles retrieved from {ds_pc.datasource.name} for "
                          f"{symbol} to {to_date}.")

                # Prepare the dataframe for bulk upsert by adding the datasource symbol.
                data['datasource_symbol_id'] = datasource_symbol.id

                # Update or insert. We need he data, the table name and the list of unique fields.
                unique_fields = ['datasource_symbol_id', 'time', 'period']
                table = models.Candle.objects.model._meta.db_table
                DatabaseUtility.bulk_insert_or_update(data=data, table=table, unique_fields=unique_fields)
            except datasource.DataNotAvailableException as ex:
                log.warning(ex)
    else:
        # Inactive
        log.debug(f"Task running for DataSourceCandlePeriod {ds_pc}.")


@shared_task(name='retrieve_symbols', queue='pricedata')
def retrieve_symbols(datasource_id):
    """
    Retrieves symbols for datasource and populates in application database
    :param datasource_id:
    :return:
    """
    from pricedata import models  # Imported when needed, due to circular dependency

    # Logger
    log = logging.getLogger(__name__)

    # Get the datasource candleperiod mapping class from its id
    ds = models.DataSource.objects.get(id=datasource_id)

    # Only if active
    if ds.active:
        # Get an instance of the datasource implementation to retrieve symbols from
        instance = datasource.DataSourceImplementation.instance(ds.name)

        # Get symbols from instance
        ds_symbols = instance.get_symbols()

        # Update the database.
        for ds_symbol in ds_symbols:
            # Get symbol if it already exists, otherwise create it
            symbols = models.Symbol.objects.filter(name=ds_symbol['symbol_name'])
            if len(symbols) > 0:
                symbol = symbols[0]
            else:
                # Add it.
                symbol = models.Symbol(name=ds_symbol['symbol_name'], instrument_type=ds_symbol['instrument_type'])
                symbol.save()

            # Get the symbol info. It is all fields from ds_symbol except for symbol_name and instrument_type
            symbol_info = ds_symbol
            del symbol_info['symbol_name']
            del symbol_info['instrument_type']

            # Create a DataSourceSymbol if it doesn't already exist. Update it if it does.
            ds_symbols = models.DataSourceSymbol.objects.filter(datasource=ds, symbol=symbol)

            if len(ds_symbols) == 0:
                ds_symbol = models.DataSourceSymbol(datasource=ds, symbol=symbol, symbol_info=json.dumps(symbol_info))
            else:
                ds_symbol = ds_symbols[0]
                ds_symbol.symbol_info = json.dumps(symbol_info)

            # Save it
            ds_symbol.save()


# noinspection PyTypeChecker
@shared_task(name='create_summary_data')
def create_summary_data():
    """
    Creates summary data from candles for use by the data quality dashboards and charts.
    :return:
    """

    from pricedata import models  # Imported when needed, due to circular dependency

    # Create the batch
    batch = models.SummaryBatch(time=timezone.now(), status=models.SummaryBatch.STATUS_IN_PROGRESS)
    batch.save()

    # Get all price data
    sql = """SELECT	dscp.id AS datasource_candleperiod_id,
                    dss.id AS datasource_symbol_id,
                    dss.symbol_id AS symbol_id,
                    dscp.period AS period,
                    cdl.time AS time
            FROM pricedata_datasourcesymbol dss
                    INNER JOIN pricedata_candle cdl
                        ON cdl.datasource_symbol_id = dss.id
                    INNER JOIN pricedata_datasourcecandleperiod dscp
                        ON dss.datasource_id = dscp.datasource_id  AND 
                            cdl.period = dscp.period
            WHERE dss.retrieve_price_data = true"""

    price_data = pd.read_sql_query(sql=sql, con=connection)

    # Our summary views will contain min, max and mean aggregates for each aggregation period
    aggs = {'minutes': 'T', 'hours': 'H', 'days': 'D', 'weeks': 'W', 'months': 'M'}

    # We will create 2 summary views, one by datasource and one across datasources
    summary_by_ds_groupby = ['datasource_symbol_id', 'datasource_candleperiod_id']
    symmary_across_ds_groupby = ['symbol_id', 'period']
    group_bys = [summary_by_ds_groupby, symmary_across_ds_groupby]
    tables = [models.SummaryMetric.objects.model._meta.db_table,
              models.SummaryMetricAllDatasources.objects.model._meta.db_table]

    for i in range(0, 2):
        group_by = group_bys[i]
        table = tables[i]

        grouped = price_data.groupby(group_by).agg(first_candle_time=('time', 'min'), last_candle_time=('time', 'max'),
                                                   num_candles=('time', 'count'))

        for key in aggs:
            # Get counts for aggregation period, then group by datasource symbol and datasource candleperiod to get min,
            # max and avg counts for each aggregation period
            agg_period_ungrouped = \
                price_data.groupby(group_by + [pd.Grouper(key='time', freq=aggs[key]), ]).agg(count=('time', 'count'))

            agg_period_grouped = agg_period_ungrouped.groupby(group_by).agg(
                min=('count', 'min'), max=('count', 'max'), avg=('count', 'median'))

            # Rename columns to include aggregation period key, then merge into original dataframe
            agg_period_grouped = agg_period_grouped.rename(
                columns={'min': f'{key}_min', 'max': f'{key}_max', 'avg': f'{key}_avg'})
            grouped = grouped.join(agg_period_grouped, on=group_by)

        # Reset the grouped index so we end up with a flat dataframe
        grouped = grouped.reset_index()

        # Add the summary batch id
        grouped['summary_batch_id'] = batch.id

        # Insert into db
        DatabaseUtility.bulk_insert_or_update(data=grouped, table=table, batch_size=100)

    # We will also aggregate the times across each aggregation period and symbol for all datasources and periods.
    # We will only aggregate enough data for each aggregation period for maxplots plots
    grouped = None
    group_by = ['datasource_symbol_id', 'datasource_candleperiod_id']

    for key in aggs:
        # Create grouped for agg period
        agg_grouped = price_data.groupby(group_by + [pd.Grouper(key='time', freq=aggs[key]), ]).size().reset_index(
            name='num_candles')

        # Add aggregation period and batch
        agg_grouped['aggregation_period'] = key
        agg_grouped['summary_batch_id'] = batch.id

        # Add agg group to grouped
        grouped = agg_grouped if grouped is None else grouped.append(agg_grouped)

    # Insert into db
    table = models.SummaryAggregation.objects.model._meta.db_table
    DatabaseUtility.bulk_insert_or_update(data=grouped, table=table,  batch_size=100)

    # Batch complete
    batch.status = models.SummaryBatch.STATUS_COMPLETE
    batch.save()

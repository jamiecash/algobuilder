import logging

from background_task import background

from pricedata.datasource import DataSourceImplementation
from pricedata.models import DataSourceCandlePeriod, DataSourceSymbol


@background(schedule=0, queue='price-data')
def retrieve_price_data(datasource_candleperiod_id: int) -> None:

    # Logger
    log = logging.getLogger(__name__)

    # Get the datasource candleperiod mapping class from its id
    ds_pc = DataSourceCandlePeriod.objects.get(id=datasource_candleperiod_id)

    # Only continue if active
    if ds_pc.active:
        # Get candles
        log.debug(f"Getting price data for {ds_pc.datasource.name} for period {ds_pc.period}.")

        # Get datasource instance to retrieve data from
        ds_instance = DataSourceImplementation.instance(ds_pc.datasource.name)

        # Get the symbols where we will retrieving price data for
        datasource_symbols = DataSourceSymbol.objects.filter(datasource=ds_pc.datasource, retrieve_price_data=True)
    else:
        # Inactive, we have an orphaned task. Log warning.
        log.warning(f"Task running for inactive DataSourceCandlePeriod {DataSourceCandlePeriod}.")

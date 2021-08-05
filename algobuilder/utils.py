"""
A collection of utilities for use across apps
"""
import functools
import logging
import math
import numpy as np
import pandas as pd
from typing import List

from django.core.cache import caches, InvalidCacheBackendError
from django.db import connection


# TARGET PROJECT THEME: Caching
# TODO Enable support for static methods.
class _Cache(object):
    """
    Decorator to retrieve dataframe output of decorated function from Django cache if it exists. If it doesn't it will
    retrieve from decorated function and store in cache.

    This is only suitable for decorating functions that return a pandas dataframe. It does not work with static methods.

    Dependency: Django must be set up with caching
    """

    # Logger
    __log = logging.getLogger(__name__)

    # Cache name.
    __cache_name = None

    # Wrapped function
    __func = None

    def __init__(self, func, cache_name='default'):
        """
        Decorator to cache the output of a function.
        :param func: The function being decorated
        :param cache_name: The name of the Django cache. Default will use the default cache.

        To configure Django caching see https://docs.djangoproject.com/en/3.2/topics/cache/
        """
        functools.update_wrapper(self, func)
        self.__func = func
        self.__cache_name = cache_name

    def __call__(self, *args, **kwargs):
        """
        Check if it exists in the cache, if not, run the func and store output in cache, else retrieve from cache
        :param args:
        :param kwargs:
        :return: return the decorated function.
        """
        # Session key is func name and passed parameters with spaces and control characters removed and reduced to
        # 200 characters max
        cache_key = f"{self.__func.__name__}_{','.join([f'{x}' for x in args])}_" \
                    f"{','.join([f'{x}={kwargs[x]}' for x in kwargs.keys()])}"
        for char in [" ", "\n"]:
            cache_key = cache_key.replace(char, "")
        cache_key = cache_key[0:200] if len(cache_key) > 200 else cache_key

        # Try and get from cache. If it doesnt exist in cache, then return from wrapped function.
        try:
            cache = caches[self.__cache_name]

            # Get from cache if it exists
            json_txt = cache.get(cache_key, None)

            if json_txt is not None:
                self.__log.debug(f"Retrieved {cache_key} from cache.")
                ret = pd.read_json(json_txt, orient='table')
            else:
                self.__log.debug(f"Retrieving {cache_key} from function.")
                ret = self.__func(self, *args, **kwargs)

                # Save it in cache as JSON
                cache.set(cache_key, ret.to_json(orient='table'))
        except InvalidCacheBackendError as ex:
            # If cache doesnt exist, or there was an error , we will retrieve from the wrapped function.
            self.__log.debug(f"Retrieving {cache_key} from function. Error accessing cache", ex)
            ret = self.__func(self, *args, **kwargs)

        return ret


# wrap _Cache to allow for deferred calling
def django_cache(func=None, cache_name=None):
    if func:
        return _Cache(func)
    else:
        def wrapper(function):
            return _Cache(function, cache_name=cache_name)

        return wrapper


# TARGET PROJECT THEME: Database
class DatabaseUtility:
    @staticmethod
    def bulk_insert_or_update(data: pd.DataFrame, table: str, unique_fields=None, batch_size=None):
        """
        Bulk insert or update (upsert) of price data. If unique fields already exists, then update else insert

        :param data: The pandas dataframe to insert / update to db. The columns in the dataframe must match the table
            columns.
        :param table: The name of the table to update
        :param unique_fields: Fields that will raise the unique key constraint on insert. If none are provided, then we
            will just do a straight insert rather than upsert.
        :param batch_size: Maximum number of rows to update in one go. If None, then no batching
        :return:
        """

        # Logger
        log = logging.getLogger(__name__)

        # Do we have any data
        if data is not None and len(data.index) > 0:
            # Get batches if we are batching. If not create a single batch with all the data
            batches = [data, ] if not batch_size else np.array_split(data, math.ceil(len(data.index) / batch_size))
            log.debug(f'Bulk INSERT / UPDATE to {table}. Rowcount: {len(data.index)}.')
            if batch_size is not None:
                log.debug(f'Update split into {len(batches)} batches of maximum {batch_size} updates.')  # TODO DEBUG

            for i in range(0, len(batches)):
                batch = batches[i]
                log.debug(f'Bulk INSERT / UPDATE to {table}. Batch {i + 1} of {len(batches)}.')

                if unique_fields is None:
                    # Insert
                    DatabaseUtility.__bulk_insert_batch(batch, table)
                else:
                    # UPSERT
                    DatabaseUtility.__bulk_upsert_batch(data, table, unique_fields)
            else:
                log.debug(f"No data to save.")

    @staticmethod
    def __bulk_insert_batch(data: pd.DataFrame, table: str):
        """
        Bulk insert for a single update from a batch. Called by bulk_insert_or_update
        :param data:
        :param table:
        :return:
        """
        # Logger
        log = logging.getLogger(__name__)

        # Create the SQL
        sqlvals = DatabaseUtility.__get_sql_insert_values_from_dataframe(data)
        sql = f"INSERT INTO {table} ({','.join(list(data.columns))}) VALUES {','.join(sqlvals)}"

        # Execute
        log.debug(f"INSERTING {len(data.index)} rows to {table}.")
        connection.cursor().execute(sql)

    @staticmethod
    def __bulk_upsert_batch(data: pd.DataFrame, table: str, unique_fields: List[str]):
        """
        Bulk insert for a single update from a batch. Called by bulk_insert_or_update
        :param data:
        :param table:
        :return:
        """
        # Logger
        log = logging.getLogger(__name__)

        # Get create fields from dataframe and the update fields as the create fields - unique fields
        create_fields = data.columns
        update_fields = set(create_fields) - set(unique_fields)

        # Build build list of x = excluded.x columns for SET part of sql
        on_duplicates = []
        for field in update_fields:
            on_duplicates.append(field + "=excluded." + field)

        # Create the SQL
        sqlvals = DatabaseUtility.__get_sql_insert_values_from_dataframe(data)
        sql = f"INSERT INTO {table} ({','.join(list(data.columns))}) VALUES {','.join(sqlvals)} " \
              f"ON CONFLICT ({','.join(list(unique_fields))}) DO UPDATE SET {','.join(on_duplicates)}"

        # Execute
        log.debug(f"UPSERTING {len(data.index)} rows to {table}.")
        connection.cursor().execute(sql)

    @staticmethod
    def __get_sql_insert_values_from_dataframe(data):
        """
        Creates the values part of a SQL query for insert or update from a dataframes data
        :param data:
        :return:
        """
        # Get the values from the data
        values = [tuple(x) for x in data.to_numpy()]

        # Create cursor
        cursor = connection.cursor()

        # Mogrify values to bind into sql.
        placeholders = ','.join(['%s' for _ in data.columns])
        sqlvals = [cursor.mogrify(f"({placeholders})", val).decode('utf8') for val in values]

        return sqlvals

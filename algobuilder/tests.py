import random

import pandas as pd
from django.test import TestCase

from algobuilder.utils import django_cache, DatabaseUtility
from pricedata.models import Symbol


class DjangoCacheTest(TestCase):
    def test_decorator(self):
        """
        Test that the django_cache decorator returns the cached version of a method retirn dataframe rather than a new
        one.
        :return:
        """

        # django cache only works with non static methods so our test methods will need to be declared inside a class.
        class DecoratorTestClass:
            # Declare function to return dataframe. Will contain a random number to make sure different calls to
            # function will return different sets of data. The parameter doesnt do anything but will be used to assert
            # that calls to the decorated function with different params will not return from the cache.
            def get_data(self, parameter: str):
                data = []
                for i in range(0, 20):
                    data.append([random.randint(0, 1000000), i])
                return pd.DataFrame(columns=['random', 'counter'], data=data)

            # Declare a decorated version of this function
            @django_cache
            def get_data_decorated(self, parameter: str):
                return DecoratorTestClass().get_data(parameter)

        # Get the data twice from the undecorated version. The results should be different
        data1 = DecoratorTestClass().get_data('test')
        data2 = DecoratorTestClass().get_data('test')
        self.assertFalse(data1.equals(data2))

        # Now do the same, but this time from the decorated version. The results should be the same
        data1 = DecoratorTestClass().get_data_decorated('test')
        data2 = DecoratorTestClass().get_data_decorated('test')
        self.assertTrue(data1.equals(data2))

        # Repeat the decorated test, but this time using different parameters. The results should be different.
        data1 = DecoratorTestClass().get_data_decorated('test')
        data2 = DecoratorTestClass().get_data_decorated('test2')
        self.assertFalse(data1.equals(data2))


class DatabaseUtilityTest(TestCase):
    def test_bulk_insert(self):
        """
        Test that bulk insert of dataframe creates data that can be used by ORM
        """

        # 100 rows of symbol data
        data = []
        for i in range(0, 100):
            data.append([f'Symbol_{i}', 'FOREX'])
        df = pd.DataFrame(columns=['name', 'instrument_type'], data=data)

        # Bulk insert
        DatabaseUtility.bulk_insert_or_update(data=df, table='pricedata_symbol')

        # Get all symbols and check that we have 100
        symbols = Symbol.objects.all()
        self.assertEqual(len(symbols), 100)

    def test_bulk_upsert(self):
        """
        Test that when inserting duplicate rows and defining unique columns that duplicates are updated rather than
        inserted#
        """

        # 100 rows of symbol data
        data = []
        for i in range(0, 100):
            data.append([f'Symbol_{i}', 'FOREX'])
        df = pd.DataFrame(columns=['name', 'instrument_type'], data=data)

        # Bulk insert
        DatabaseUtility.bulk_insert_or_update(data=df, table='pricedata_symbol')

        # 5 new rows and 5 rows with duplicate symbol name but different instrument type
        data = []
        for i in range(95, 105):
            data.append([f'Symbol_{i}', 'CFD'])
        df = pd.DataFrame(columns=['name', 'instrument_type'], data=data)

        # Bulk upsert
        DatabaseUtility.bulk_insert_or_update(data=df, table='pricedata_symbol', unique_fields=['name'])

        # Get all symbols. We should have 105, 95 with an instrument type of FOREX and 10 with an instrument type of CFD
        symbols = Symbol.objects.all()
        self.assertEqual(len(symbols), 105)

        symbols = Symbol.objects.filter(instrument_type='FOREX')
        self.assertEqual(len(symbols), 95)

        symbols = Symbol.objects.filter(instrument_type='CFD')
        self.assertEqual(len(symbols), 10)

    def test_batching(self):
        """
        Test that batching of inserts results in the correct number of records
        :return:
        """
        # 1000 rows of symbol data
        data = []
        for i in range(0, 1000):
            data.append([f'Symbol_{i}', 'FOREX'])
        df = pd.DataFrame(columns=['name', 'instrument_type'], data=data)

        # Bulk insert
        DatabaseUtility.bulk_insert_or_update(data=df, table='pricedata_symbol', batch_size=100)

        # Get all symbols. We should have 1000
        symbols = Symbol.objects.all()
        self.assertEqual(len(symbols), 1000)






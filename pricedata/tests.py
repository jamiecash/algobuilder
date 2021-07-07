from django.test import TestCase
from unittest.mock import patch

from pricedata.models import DataSource


# Tests for the data model
class DataSourceTests(TestCase):

    def test_get_connection_param(self):
        """
        get_connection_param returns a data source connection param passed as a string representation of a dict. Test
        that it works for both string and int params and test that badly formatted connection params are handled
        elegantly.
        """

        # Test valid str and int params
        connection_params = "{'str_param': 'str_val', 'int_param': 7}"
        ds = DataSource(connection_params=connection_params)
        self.assertEqual(ds.get_connection_param('str_param'), 'str_val')
        self.assertEqual(ds.get_connection_param('int_param'), 7)

        # Test badly formatted connection params string. We will miss the closing ' on the first param name
        connection_params = "{'str_param: 'str_val', 'int_param': 7}"
        ds = DataSource(connection_params=connection_params)
        self.assertRaises(SyntaxError, ds.get_connection_param, ['str_param'])

    @patch('pricedata.datasource.DataSourceImplementation')
    def test_save(self, mock):
        """
        When a datasource is saved, it should call DataSourceImplementation.configure passing itself. We will test
        using a mock DataSourceImplementation.
        :return:
        """

        # Create datasource with a name that we can test and save it and create another datasource which isnt passed
        # for comparison
        ds = DataSource(name='test')
        ds.save()
        unused_ds = DataSource(name='unused')

        # Assert that our mock had its configure function called exactly once
        self.assertTrue(mock.configure.call_count == 1)

        # And assert that the datasource was passed and not a different one
        call_args_list = mock.configure.call_args_list
        self.assertTrue(((), {'datasource': ds}) in call_args_list)
        self.assertFalse(((), {'datasource': unused_ds}) in call_args_list)

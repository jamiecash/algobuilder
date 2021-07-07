from django.test import TestCase, SimpleTestCase

from pricedata.models import DataSource


# Tests for the data model
class DataSourceTests(SimpleTestCase):

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

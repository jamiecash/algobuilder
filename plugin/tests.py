from django.test import TestCase
from unittest.mock import patch

from plugin import models


class PluginTests(TestCase):
    def test_save(self):
        """
        When a plugin is saved, it should schedule a task to load its requirements.
        :return:
        """

        # Create plugin save it
        plugin = models.Plugin(module_filename='testfilename.py', requirements_file='testfilename.txt')
        plugin.save()

        # Test that a task was created to prepare this datasource
        # TODO. Check that task has been created and recieved. We will need to mock celery. Not sure how we can make
        #  this a valid test.


class PluginPreparerTest(TestCase):
    def test_prepare(self):
        """
        Test that the prepare method installs the requirements and creates the PluginClass's for the module.
        :return:
        """
        # TODO. Implement this test
        pass



import importlib
import logging

from django.db import models

from plugin.tasks import install_plugin


class Plugin(models.Model):
    """
    A plugin module to AlgoBuilder. Can contain many PluginClass's.
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The path to the plugin module and requirements file
    module_filename = models.FileField(max_length=200, upload_to='plugin/plugins')
    requirements_file = models.FileField(max_length=200, upload_to='plugin/requirements')

    # Whether the module us installed
    installed = models.BooleanField(default=False)

    # Module. Create only once on module property method
    __module = None

    @property
    def module_name(self):
        """
        Gets the module name from the module filename
        :return:
        """
        # path to module. Convert file name to module name
        replaces = [('/', '.'), ('.py', '')]  # first ('plugin/', ''),  ?
        module_path = self.module_filename.name
        for rep in replaces:
            module_path = module_path.replace(rep[0], rep[1])

        return module_path

    @property
    def module(self):
        if self.__module is None:
            try:
                self.__module = importlib.import_module(self.module_name)
            except NameError as ex:
                raise NameError(f'Module {self.module_name} could not be imported.', ex)

        return self.__module

    def save(self, *args, **kwargs):
        """
        Override save to schedule a task to install the plugin requirements.
        :param args:
        :param kwargs:
        :return:
        """
        super().save(*args, **kwargs)
        install_plugin.delay(plugin_id=self.id)

    def __repr__(self):
        return f"Plugin(module_name={self.module_name}, requirements_file={self.requirements_file})"

    def __str__(self):
        return f"{self.module_name}"


class PluginClass(models.Model):
    """
    A class available in a model. Has a name and a type. Type can be a:
        DataSourceImplementation;
        TODO: List other supported plugins here.

    This will be auto populated when a plugin is setup, and hence not available on the admin.
    """

    # Logger
    __log = logging.getLogger(__name__)

    # The Plugin
    plugin = models.ForeignKey('Plugin', on_delete=models.CASCADE)

    # The class name
    name = models.CharField(max_length=100)

    # The type
    plugin_type = models.CharField(max_length=50)

    # The class. Will be created on plugin_class property method
    __class = None

    @property
    def plugin_class(self):
        """
        Returns the class
        :return:
        """
        if self.__class is None:
            try:
                self.__class = getattr(self.plugin.module, self.name)
            except NameError as ex:
                raise NameError(
                    f'Class {self.name} could not be found in module {self.plugin.module_name}.', ex)

        return self.__class

    def __repr__(self):
        return f"PluginClass(plugin={self.plugin}, name={self.name}, type={self.plugin_type})"

    def __str__(self):
        return f"{self.name}"


import importlib
import inspect
import logging
import subprocess
import sys

from background_task import background


class PluginPreparer:
    """
    A class to prepare a plugin. Runs as a task so that web form isn't tied up on save.
    """

    # Logger
    __log = logging.getLogger(__name__)

    @staticmethod
    @background(schedule=0, queue='plugin_prep')
    def prepare(plugin_id: int):
        from plugin import models  # Imported when needed, due to circular dependency

        # Get the plugin model id
        plugin = models.Plugin.objects.get(id=plugin_id)

        # Configure the plugin

        # Install libraries in requirements file. This must be done prior to instance being created due to dependencies
        if plugin.requirements_file.name != '':
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r',
                                       f'{plugin.requirements_file.name}'])
            except subprocess.CalledProcessError as ex:
                PluginPreparer.__log.warning(f"Requirements for Plugin {plugin.module_name} could not be installed.",
                                             ex)

        # Import the module
        module = importlib.import_module(plugin.module_name)

        # Get classes and types. Only get classes declared in module, not those imported.
        members = inspect.getmembers(module, inspect.isclass)
        classes = [cl[1] for cl in members if cl[1].__module__ == module.__name__]

        for c in classes:
            # Get the base class. This will determine type. This will be the first base class as we will not be using
            # multiple inheritance for plugins.
            base = c.__bases__[0]
            plugin_type = base.__name__

            # Create it
            models.PluginClass(plugin=plugin, name=c.__name__, plugin_type=plugin_type).save()



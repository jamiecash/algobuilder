from django.contrib import admin
from plugin.models import Plugin

# Override titles etc.
admin.site.site_title = "AlgoBuilder site admin"
admin.site.site_header = 'AlgoBuilder administration'
admin.site.index_title = 'AlgoBuilder administration'


# Plugins. Has callable to display the number of classes in the module, and callable to display the path to the
# requirements file as text, not a link
@admin.display(description='Num Classes')
def num_classes(obj):
    return obj.pluginclass_set.count()


@admin.display(description='Requirements File')
def requirements_file_name(obj):
    return obj.requirements_file.name


@admin.register(Plugin)
class PluginAdmin(admin.ModelAdmin):
    fields = ("module_filename", "requirements_file")
    list_display = ("module_name", requirements_file_name, num_classes)
    readonly_fields = ("module_name", requirements_file_name)





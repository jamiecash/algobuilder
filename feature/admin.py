from django.contrib import admin
from . import models

# Override titles etc.
admin.site.site_title = "AlgoBuilder site admin"
admin.site.site_header = 'AlgoBuilder administration'
admin.site.index_title = 'AlgoBuilder administration'


# Feature.
@admin.register(models.Feature)
class FeatureAdmin(admin.ModelAdmin):
    fields = ("name", "pluginclass", "calculation_period", "calculation_frequency", "active")
    list_display = ("name", "pluginclass", "calculation_period", "calculation_frequency", "active")
    list_editable = ("calculation_frequency", "active",)


# FeatureExecutionSymbol. Not registered as used inline on FeatureExecution
class FeatureExecutionDataSourceSymbol(admin.ModelAdmin):
    list_display = ("datasource_symbol", "candle_period", "active")
    list_editable = ("datasource_symbol", "candle_period", "active")
    list_filter = ("datasource_symbol", "candle_period", "active")


# Symbols for FeatureExecution will be administered on datasource admin page
class DatasourceSymbols(admin.TabularInline):
    model = models.FeatureExecutionDataSourceSymbol
    fields = ("feature_execution", "datasource_symbol", "candle_period", "active")
    extra = 0


# FeatureExecution. Symbols added inline
@admin.register(models.FeatureExecution)
class FeatureExecutionAdmin(admin.ModelAdmin):
    fields = ("feature", "name", "active")
    list_display = ("feature", "name", "active")

    inlines = [DatasourceSymbols]

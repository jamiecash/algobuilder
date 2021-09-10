from django.contrib import admin
from . import models

# Override titles etc.
admin.site.site_title = "AlgoBuilder site admin"
admin.site.site_header = 'AlgoBuilder administration'
admin.site.index_title = 'AlgoBuilder administration'


# Feature.
@admin.register(models.Feature)
class FeatureAdmin(admin.ModelAdmin):
    fields = ("name", "pluginclass", "active")
    list_display = ("name", "pluginclass", "active")
    list_editable = ("active",)


# FeatureExecutionSymbol. Mpt registered as used inline on FeatureExecution
class FeatureExecutionDataSourceSymbol(admin.ModelAdmin):
    list_display = ("datasource_symbol", "active")
    list_editable = ("datasource_symbol", "active")
    list_filter = ("datasource_symbol", "active")


# Symbols for FeatureExecution will be administered on datasource admin page
class DatasourceSymbols(admin.TabularInline):
    model = models.FeatureExecutionDataSourceSymbol
    fields = ("feature_execution", "datasource_symbol", "active")
    extra = 0


# FeatureExecution. Symbols added inline
@admin.register(models.FeatureExecution)
class FeatureExecutionAdmin(admin.ModelAdmin):
    # TODO Restrict choices for candle_period to those available in datasource_candleperiods
    fields = ("feature", "candle_period", "calculation_period", "active")
    list_display = ("feature", "candle_period", "calculation_period", "symbols", "active")

    inlines = [DatasourceSymbols]

from django.contrib import admin
from django import forms

# Register your models here.
from plugin.models import PluginClass
from . import models

# Override titles etc.
admin.site.site_title = "AlgoBuilder site admin"
admin.site.site_header = 'AlgoBuilder administration'
admin.site.index_title = 'AlgoBuilder administration'


# DataSourceCandlePeriod. Not registered as used in line on DataSource admin
class DataSourceCandlePeriodAdmin(admin.ModelAdmin):
    list_display = ("datasource", "period", "start_from", "active")
    list_editable = ("period", "start_from", "active")
    list_filter = ("datasource__name", "period")


# CandlePeriods will be administered on datasource admin page
class CandlePeriods(admin.TabularInline):
    model = models.DataSourceCandlePeriod
    extra = 0


# DataSource. Edit candle periods inline
@admin.register(models.DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    fields = ("name", "pluginclass", "connection_params")
    list_display = ("name", "pluginclass", "connection_params")

    inlines = [CandlePeriods]


# Symbol
@admin.register(models.Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("name", "instrument_type")
    list_editable = ("instrument_type",)
    list_filter = ("instrument_type",)
    search_fields = ["name", "instrument_type"]


# DataSourceSymbol
@admin.action(description='Set retrieve price data for all')
def set_retrieve_price_data_for_all(modeladmin, request, queryset):
    queryset.update(retrieve_price_data=True)


@admin.action(description='Unset retrieve price data for all')
def unset_retrieve_price_data_for_all(modeladmin, request, queryset):
    queryset.update(retrieve_price_data=False)


@admin.register(models.DataSourceSymbol)
class DataSourceSymbolAdmin(admin.ModelAdmin):

    def get_symbol_instrument_type(self, obj):
        return obj.symbol.instrument_type

    get_symbol_instrument_type.admin_order_field = 'symbol'  # Allows column order sorting
    get_symbol_instrument_type.short_description = 'Instrument Type'  # Renames column head

    list_display = ("datasource", "symbol", "get_symbol_instrument_type", "retrieve_price_data")
    list_editable = ("retrieve_price_data",)
    list_filter = ("symbol__instrument_type", "retrieve_price_data")
    search_fields = ["symbol__name", "symbol__instrument_type"]
    actions = [set_retrieve_price_data_for_all, unset_retrieve_price_data_for_all]


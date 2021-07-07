from django.contrib import admin

# Register your models here.
from .models import DataSource, DataSourceCandlePeriod, DataSourceSymbol, Symbol

# DataSource
admin.site.register(DataSource)


# Symbol
@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("name", "instrument_type")
    list_editable = ("instrument_type",)
    list_filter = ("instrument_type",)


# DataSourceSymbol
@admin.action(description='Set retrieve price data for all')
def set_retrieve_price_data_for_all(modeladmin, request, queryset):
    queryset.update(retrieve_price_data=True)


@admin.action(description='Unset retrieve price data for all')
def unset_retrieve_price_data_for_all(modeladmin, request, queryset):
    queryset.update(retrieve_price_data=False)


@admin.register(DataSourceSymbol)
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


# DataSourceCandlePeriod
@admin.register(DataSourceCandlePeriod)
class DataSourceCandlePeriodAdmin(admin.ModelAdmin):
    list_display = ("datasource", "period", "start_from")
    list_editable = ("period", "start_from")
    list_filter = ("datasource__name", "period")

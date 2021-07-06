from django.contrib import admin

# Register your models here.
from .models import DataSource, DataSourceSymbol

admin.site.register(DataSource)
admin.site.register(DataSourceSymbol)

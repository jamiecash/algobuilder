# Generated by Django 3.2.5 on 2021-09-13 08:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Plugin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_filename', models.FileField(max_length=200, upload_to='plugin/plugins')),
                ('requirements_file', models.FileField(blank=True, max_length=200, upload_to='plugin/requirements')),
                ('installed', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='PluginClass',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('plugin_type', models.CharField(max_length=50)),
                ('plugin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='plugin.plugin')),
            ],
        ),
    ]

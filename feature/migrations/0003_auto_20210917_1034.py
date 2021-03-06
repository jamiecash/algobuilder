# Generated by Django 3.2.5 on 2021-09-17 09:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
        ('feature', '0002_alter_featureexecutionresult_unique_together'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='featureexecution',
            name='calculation_period',
        ),
        migrations.RemoveField(
            model_name='featureexecution',
            name='candle_period',
        ),
        migrations.RemoveField(
            model_name='featureexecution',
            name='task',
        ),
        migrations.AddField(
            model_name='feature',
            name='calculation_frequency',
            field=models.CharField(default='1S', max_length=6),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='feature',
            name='calculation_period',
            field=models.CharField(default='1S', max_length=6),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='feature',
            name='task',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='django_celery_beat.periodictask'),
        ),
        migrations.AddField(
            model_name='featureexecution',
            name='name',
            field=models.CharField(default='BOB', max_length=20, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='featureexecutiondatasourcesymbol',
            name='candle_period',
            field=models.CharField(choices=[('1S', '1 Second'), ('5S', '5 Second'), ('10S', '10 Second'), ('15S', '15 Second'), ('30S', '30 Second'), ('1M', '1 Minute'), ('5M', '5 Minute'), ('10M', '10 Minute'), ('15M', '15 Minute'), ('30M', '30 Minute'), ('1H', '1 Hour'), ('3H', '3 Hour'), ('6H', '6 Hour'), ('12H', '12 Hour'), ('1D', '1 Day'), ('1W', '1 Week'), ('1MO', '1 Month')], default='1D', max_length=3),
            preserve_default=False,
        ),
    ]

# Generated by Django 3.1.1 on 2020-10-06 07:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CovidOverview',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('confirmed_cases', models.PositiveIntegerField(verbose_name='The total number of confirmed cases')),
                ('confirmed_cases_yesterday', models.PositiveIntegerField(verbose_name='Number of confirmed cases in the previous day')),
                ('confirmed_cases_today', models.PositiveIntegerField(verbose_name='Number of confirmed cases for today')),
                ('active_cases', models.PositiveIntegerField(verbose_name='The total number of active cases')),
                ('total_recovered', models.PositiveIntegerField(verbose_name='The total number of recovered patients')),
                ('total_deaths', models.PositiveIntegerField(verbose_name='The total number of deaths of COVID-19 positive patients')),
                ('hospitalized_count', models.PositiveIntegerField(verbose_name='The total number of hospitalized patients')),
                ('performed_tests', models.PositiveIntegerField(verbose_name='The total number of performed tests')),
                ('performed_tests_yesterday', models.PositiveIntegerField(verbose_name='Number of tests performed in the previous day')),
            ],
        ),
        migrations.CreateModel(
            name='NUTS_0_AREA',
            fields=[
                ('name', models.CharField(max_length=80)),
                ('code', models.CharField(max_length=2, primary_key=True, serialize=False)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NUTS_1_AREA',
            fields=[
                ('name', models.CharField(max_length=80)),
                ('code', models.CharField(max_length=3, primary_key=True, serialize=False)),
                ('nuts_higher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_0_area')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NUTS_2_AREA',
            fields=[
                ('name', models.CharField(max_length=80)),
                ('code', models.CharField(max_length=4, primary_key=True, serialize=False)),
                ('nuts_higher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_1_area')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NUTS_3_AREA',
            fields=[
                ('name', models.CharField(max_length=80)),
                ('code', models.CharField(max_length=5, primary_key=True, serialize=False)),
                ('nuts_higher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_2_area')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PerformedTests',
            fields=[
                ('date', models.DateField(primary_key=True, serialize=False)),
                ('test_count', models.PositiveIntegerField(verbose_name='Total number of performed tests at given day')),
            ],
        ),
        migrations.CreateModel(
            name='WeeklyDeaths',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveSmallIntegerField()),
                ('week_number', models.PositiveSmallIntegerField()),
                ('date_start', models.DateField(verbose_name='First day of the week')),
                ('date_end', models.DateField(verbose_name='Last day of the week')),
                ('death_count_1', models.PositiveIntegerField(verbose_name='Death count for 0-14')),
                ('death_count_2', models.PositiveIntegerField(verbose_name='Death count for 15-39')),
                ('death_count_3', models.PositiveIntegerField(verbose_name='Death count for 40-64')),
                ('death_count_4', models.PositiveIntegerField(verbose_name='Death count for 65-85')),
                ('death_count_5', models.PositiveIntegerField(verbose_name='Death count for 85+')),
            ],
            options={
                'unique_together': {('year', 'week_number')},
            },
        ),
        migrations.CreateModel(
            name='NUTS_4_AREA',
            fields=[
                ('name', models.CharField(max_length=80)),
                ('code', models.CharField(max_length=6, primary_key=True, serialize=False)),
                ('nuts_higher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_3_area')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='CovidDeath',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_death', models.DateField()),
                ('age', models.PositiveSmallIntegerField(verbose_name="Person's age at death")),
                ('gender', models.CharField(max_length=1)),
                ('nuts_4_area', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_4_area')),
            ],
        ),
        migrations.CreateModel(
            name='ConfirmedCase',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField()),
                ('age', models.PositiveSmallIntegerField(verbose_name='Age at the time of the report')),
                ('gender', models.CharField(max_length=1)),
                ('nuts_4_area', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_4_area')),
                ('origin_country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='covid_app.nuts_0_area')),
            ],
        ),
    ]

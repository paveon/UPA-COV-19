from django.utils.translation import gettext_lazy as _
from django.db import models
from django.db.models import Sum
from datetime import *
from django.core.exceptions import *


class NUTS_BASE(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        abstract = True

    def __str__(self):
        return f"[{self.code}] {self.name}"


class NUTS_0_AREA(NUTS_BASE):
    code = models.CharField(max_length=2, primary_key=True)


class NUTS_1_AREA(NUTS_BASE):
    code = models.CharField(max_length=3, primary_key=True)
    nuts_higher = models.ForeignKey(NUTS_0_AREA, on_delete=models.CASCADE)


class NUTS_2_AREA(NUTS_BASE):
    code = models.CharField(max_length=4, primary_key=True)
    nuts_higher = models.ForeignKey(NUTS_1_AREA, on_delete=models.CASCADE)


class NUTS_3_AREA(NUTS_BASE):
    code = models.CharField(max_length=5, primary_key=True)
    nuts_higher = models.ForeignKey(NUTS_2_AREA, on_delete=models.CASCADE)


class NUTS_4_AREA(NUTS_BASE):
    code = models.CharField(max_length=6, primary_key=True)
    nuts_higher = models.ForeignKey(NUTS_3_AREA, on_delete=models.CASCADE)


class ConfirmedCase(models.Model):
    report_date = models.DateField()
    age = models.PositiveSmallIntegerField('Age at the time of the report')
    gender = models.CharField(max_length=1)
    # nuts_3_area = models.ForeignKey(NUTS_3_AREA, on_delete=models.CASCADE)
    nuts_4_area = models.ForeignKey(NUTS_4_AREA, on_delete=models.CASCADE)
    origin_country = models.ForeignKey(NUTS_0_AREA, on_delete=models.CASCADE)

    def __str__(self):
        return f"[Case: {self.report_date}] {self.gender} - {self.age}"


class RecoveredPerson(models.Model):
    date = models.DateField()
    age = models.PositiveSmallIntegerField('Age at the time of recovery')
    gender = models.CharField(max_length=1)
    nuts_4_area = models.ForeignKey(NUTS_4_AREA, on_delete=models.CASCADE)

    def __str__(self):
        return f"[Recovered: {self.date}] {self.gender} - {self.age}"


class CovidDeathManager(models.Manager):
    # Returns death count for specified day, results may vary from
    # 'DailyStatistics.objects.death_count' as they are both updated differently
    def death_count(self, date_of_death):
        return self.filter(date_of_death=date_of_death).count()


class CovidDeath(models.Model):
    date_of_death = models.DateField()
    age = models.PositiveSmallIntegerField('Person\'s age at death')
    gender = models.CharField(max_length=1)
    nuts_4_area = models.ForeignKey(NUTS_4_AREA, on_delete=models.CASCADE)

    objects = CovidDeathManager()

    @property
    def week_number(self):
        return self.date_of_death.isocalendar()

    def __str__(self):
        return f"[COVID-19 Death: {self.date_of_death}] {self.gender} - {self.age}"


class WeeklyDeaths(models.Model):
    class AgeCategory(models.IntegerChoices):
        ONE = 1, _('0-14')
        TWO = 2, _('15-39')
        THREE = 3, _('40-64')
        FOUR = 4, _('65-85')
        FIVE = 5, _('85+')

    year = models.PositiveSmallIntegerField()
    week_number = models.PositiveSmallIntegerField()
    date_start = models.DateField('First day of the week')
    date_end = models.DateField('Last day of the week')
    death_count_1 = models.PositiveIntegerField('Death count for 0-14')
    death_count_2 = models.PositiveIntegerField('Death count for 15-39')
    death_count_3 = models.PositiveIntegerField('Death count for 40-64')
    death_count_4 = models.PositiveIntegerField('Death count for 65-85')
    death_count_5 = models.PositiveIntegerField('Death count for 85+')

    @property
    def total_death_count(self):
        return self.death_count_1 + self.death_count_2 + self.death_count_3 + self.death_count_4 + self.death_count_5

    class Meta:
        unique_together = ('year', 'week_number')


class DailyStatsManager(models.Manager):
    def cumulative_test_count(self, begin_date=None, end_date=None):
        if begin_date and end_date:
            if end_date < begin_date:
                return 0
            selected_objects = self.filter(date__gte=begin_date, date__lte=end_date)
        elif begin_date:
            selected_objects = self.filter(date__gte=begin_date)
        elif end_date:
            selected_objects = self.filter(date__lte=end_date)
        else:
            selected_objects = self.all()
        total_tests = selected_objects.aggregate(Sum('test_count'))
        return total_tests['test_count__sum'] or 0

    def recovered_count(self, at_date):
        count = 0
        try:
            count = self.get(pk=at_date).recovered_cumulative
            previous_day_count = self.get(pk=(at_date - timedelta(days=1))).recovered_cumulative
            return count - previous_day_count
        except DailyStatistics.DoesNotExist:
            return count

    # Returns death count for specified day, results may vary from
    # 'CovidDeath.objects.death_count' as they are both updated differently
    # (this one is updated more frequently as it's completely anonymous data)
    def death_count(self, at_date):
        count = 0
        try:
            count = self.get(pk=at_date).deaths_cumulative
            previous_day_count = self.get(pk=(at_date - timedelta(days=1))).deaths_cumulative
            return count - previous_day_count
        except DailyStatistics.DoesNotExist:
            return count


class DailyStatistics(models.Model):
    date = models.DateField(primary_key=True)
    test_count = models.PositiveIntegerField('Total number of performed tests at given day')
    confirmed_case_count = models.PositiveIntegerField('Total number of confirmed cases at given day')
    recovered_cumulative = models.PositiveIntegerField('Cumulative number of recovered patients')
    deaths_cumulative = models.PositiveIntegerField('Cumulative number of deaths')

    objects = DailyStatsManager()


class CovidOverview(models.Model):
    date = models.DateTimeField()
    confirmed_cases = models.PositiveIntegerField('The total number of confirmed cases')
    confirmed_cases_yesterday = models.PositiveIntegerField('Number of confirmed cases in the previous day')
    confirmed_cases_today = models.PositiveIntegerField('Number of confirmed cases for today')
    active_cases = models.PositiveIntegerField('The total number of active cases')
    total_recovered = models.PositiveIntegerField('The total number of recovered patients')
    total_deaths = models.PositiveIntegerField('The total number of deaths of COVID-19 positive patients')
    hospitalized_count = models.PositiveIntegerField('The total number of hospitalized patients')
    performed_tests = models.PositiveIntegerField('The total number of performed tests')
    performed_tests_yesterday = models.PositiveIntegerField('Number of tests performed in the previous day')

    def save(self, *args, **kwargs):
        if not self.pk and CovidOverview.objects.exists():
            raise ValidationError('CovidOverview is a singleton model')
        return super().save(*args, **kwargs)

from django.db import models
from django.db.models import Sum
from datetime import *


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


class Deceased(models.Model):
    date_of_death = models.DateField()
    age = models.PositiveSmallIntegerField('Person\'s age at death')
    gender = models.CharField(max_length=1)
    # nuts_3_area = models.ForeignKey(NUTS_3_AREA, on_delete=models.CASCADE)
    nuts_4_area = models.ForeignKey(NUTS_4_AREA, on_delete=models.CASCADE)

    def __str__(self):
        return f"[Deceased: {self.date_of_death}] {self.gender} - {self.age}"


class PerformedTestsManager(models.Manager):
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


class PerformedTests(models.Model):
    date = models.DateField(primary_key=True)
    test_count = models.PositiveIntegerField('Total number of performed tests at given day')
    objects = PerformedTestsManager()

    def __str__(self):
        return f"[{self.date}] Test count: {self.test_count}"

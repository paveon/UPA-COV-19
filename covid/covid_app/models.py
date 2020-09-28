from django.db import models


class Region(models.Model):
    nuts3_code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.nuts3_code}: {self.name}"


class County(models.Model):
    lau1_code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.lau1_code}: {self.name}"


class Country(models.Model):
    csu_code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=80)

    def __str__(self):
        return f"{self.csu_code}: {self.name}"


class ConfirmedCase(models.Model):
    report_date = models.DateField()
    age = models.PositiveSmallIntegerField('Age at the time of the report')
    gender = models.CharField(max_length=1)
    associated_region = models.ForeignKey(Region, on_delete=models.CASCADE)
    associated_county = models.ForeignKey(County, on_delete=models.CASCADE)
    origin_country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"[Case: {self.report_date}] {self.gender} - {self.age}"


class Deceased(models.Model):
    date_of_death = models.DateField()
    age = models.PositiveSmallIntegerField('Person\'s age at death')
    gender = models.CharField(max_length=1)
    associated_region = models.ForeignKey(Region, on_delete=models.CASCADE)
    associated_county = models.ForeignKey(County, on_delete=models.CASCADE)

    def __str__(self):
        return f"[Deceased: {self.date_of_death}] {self.gender} - {self.age}"


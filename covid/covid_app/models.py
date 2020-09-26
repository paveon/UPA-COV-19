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


class Deceased(models.Model):
    date_of_death = models.DateField()
    age = models.PositiveSmallIntegerField('Person\'s age at death')
    gender = models.CharField(max_length=1)
    associated_region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True)
    associated_county = models.ForeignKey(County, on_delete=models.SET_NULL, null=True)


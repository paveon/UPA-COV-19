import pymongo
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template import loader
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import generic, View
from django.core import serializers
from django.views.decorators.cache import never_cache
from .area_codes import *
from .models import *
import json


@method_decorator(never_cache, name='dispatch')
class IndexView(generic.TemplateView):
    template_name = 'covid_app/index.html'

    def clear_db(self):
        Region.objects.all().delete()
        County.objects.all().delete()
        Deceased.objects.all().delete()
        ConfirmedCase.objects.all().delete()
        # return render(request, 'covid_app/index.html')
        # return HttpResponseRedirect(reverse('covid_app:index'))

    def import_data(self):
        Region.objects.all().delete()
        for nuts_code, region_name in NUTS_CODES_DICT.items():
            Region.objects.create(pk=nuts_code, name=region_name)

        County.objects.all().delete()
        for lau_code, county_name in LAU_CODES_DICT.items():
            County.objects.create(pk=lau_code, name=county_name)

        Country.objects.all().delete()
        for csu_code, country_name in COUNTRY_CODES_DICT.items():
            Country.objects.create(pk=csu_code, name=country_name)

        db_client = pymongo.MongoClient("mongodb://localhost:27017/")
        print(f"Existing DBs: {db_client.list_database_names()}")
        covid_db = db_client['covid_data']
        if 'daily_deaths' in covid_db.list_collection_names():
            deaths_collection = covid_db['daily_deaths']
            cursor = deaths_collection.find({})
            print(deaths_collection.estimated_document_count())
            for document in cursor:
                Deceased.objects.create(date_of_death=document['datum'],
                                        age=document['vek'],
                                        gender=document['pohlavi'],
                                        associated_region=Region.objects.get(pk=document['kraj_nuts_kod']),
                                        associated_county=County.objects.get(pk=document['okres_lau_kod']))

    def __init__(self):
        super().__init__()
        self.action_key = None
        self.response = {}
        self.context = {}
        self.actions = {
            'import_data': self.import_data,
            'clear_db': self.clear_db,
        }

    def get_context_data(self, **kwargs):
        self.context = super().get_context_data(**kwargs)
        deceased_query_set = Deceased.objects.order_by('date_of_death')
        age_data = list(deceased_query_set.values_list('age', flat=True))
        json_data = serializers.serialize('json', deceased_query_set)
        self.context['deceased_list'] = deceased_query_set[:10]
        self.context['deceased_data'] = json_data
        self.context['age_data'] = json.dumps(age_data)
        return self.context

    # def get(self, request, *args, **kwargs):
    #     if request.is_ajax():
    #         self.action_key = request.GET['action']
    #         action = self.actions[self.action_key]
    #         action()
    #         return JsonResponse(self.response)
    #     else:
    #         self.context = self.get_context_data(**kwargs)
    #         return render(request, self.template_name, self.context)

    def post(self, request, *args, **kwargs):
        self.context = self.get_context_data(**kwargs)
        self.action_key = request.POST['action']
        action = self.actions[self.action_key]
        if request.is_ajax():
            action()
            return JsonResponse(self.response)

        action()
        return render(request, self.template_name, self.context)

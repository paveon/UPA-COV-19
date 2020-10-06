import pymongo
import json
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template import loader
from django.urls import reverse
from django.apps import AppConfig, apps
from django.db.models import F, Count
from django.utils.decorators import method_decorator
from django.views import generic, View
from django.core import serializers
from django.views.decorators.cache import never_cache
from .area_codes import *
from .download_utils import download
from .models import *
from datetime import datetime

URL_COVID_OVERVIEW = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/zakladni-prehled.json'


def apply_mapping(mapping, document):
    object_dict = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            object_dict[key] = document[value]
        else:
            object_dict[key] = value.get('obj_cache').get(document[value.get('name')], value.get('default'))
    return object_dict


def import_collection(covid_db, collection_name, model_cls, mapping):
    if collection_name not in covid_db.list_collection_names():
        return
    collection = covid_db[collection_name]
    print(collection.estimated_document_count())
    cursor = collection.find({})
    objects = [model_cls(**apply_mapping(mapping, document)) for document in cursor]
    model_cls.objects.bulk_create(objects)


@method_decorator(never_cache, name='dispatch')
class IndexView(generic.TemplateView):
    template_name = 'covid_app/index.html'

    def clear_db(self):
        CovidDeath.objects.all().delete()
        ConfirmedCase.objects.all().delete()
        PerformedTests.objects.all().delete()
        WeeklyDeaths.objects.all().delete()
        # return render(request, 'covid_app/index.html')
        # return HttpResponseRedirect(reverse('covid_app:index'))

    def populate_area_tables(self):
        NUTS_0_AREA.objects.all().delete()
        NUTS_1_AREA.objects.all().delete()
        NUTS_2_AREA.objects.all().delete()
        NUTS_3_AREA.objects.all().delete()
        NUTS_4_AREA.objects.all().delete()
        covid_app = apps.get_app_config('covid_app')

        def create_areas(areas, level, higher_unit):
            model_name = f"NUTS_{level}_AREA"
            model = covid_app.get_model(model_name)
            for code, data in areas.items():
                name = data['name'] if level < 4 else data
                if higher_unit:
                    area = model.objects.create(pk=code, name=name, nuts_higher=higher_unit)
                else:
                    area = model.objects.create(pk=code, name=name)
                if level < 4:
                    sub_areas = data.get(f"NUTS_{level + 1}_AREAS")
                    if sub_areas:
                        create_areas(sub_areas, level + 1, area)

        create_areas(NUTS_0_AREAS, 0, None)
        print("Area tables populated")
        # Region.objects.bulk_create([Region(pk=code, name=name) for code, name in NUTS_CODES_DICT.items()])
        # County.objects.bulk_create([County(pk=code, name=name) for code, name in LAU_CODES_DICT.items()])
        # Country.objects.bulk_create([Country(pk=code, name=name) for code, name in COUNTRY_CODES_DICT.items()])

    def import_data(self):
        if not NUTS_0_AREA.objects.exists() \
                or not NUTS_1_AREA.objects.exists() \
                or not NUTS_2_AREA.objects.exists() \
                or not NUTS_3_AREA.objects.exists() \
                or not NUTS_4_AREA.objects.exists():
            self.populate_area_tables()

        # nuts_3_cache = {x.pk: x for x in NUTS_3_AREA.objects.all()}
        nuts_4_cache = {x.pk: x for x in NUTS_4_AREA.objects.all()}
        nuts_0_cache = {x.pk: x for x in NUTS_0_AREA.objects.all()}
        cz_cache = nuts_0_cache['CZ']

        deaths_mapping = {
            'date_of_death': 'datum',
            'age': 'vek',
            'gender': 'pohlavi',
            # 'nuts_3_area': {'name': 'kraj_nuts_kod', 'obj_cache': nuts_3_cache},
            'nuts_4_area': {'name': 'okres_lau_kod', 'obj_cache': nuts_4_cache}
        }

        case_mapping = {
            'report_date': 'datum',
            'age': 'vek',
            'gender': 'pohlavi',
            # 'nuts_3_area': {'name': 'kraj_nuts_kod', 'obj_cache': nuts_3_cache},
            'nuts_4_area': {'name': 'okres_lau_kod', 'obj_cache': nuts_4_cache},
            'origin_country': {'name': 'nakaza_zeme_csu_kod', 'obj_cache': nuts_0_cache, 'default': cz_cache}
        }

        test_mapping = {
            'date': 'datum',
            'test_count': 'prirustkovy_pocet_testu',
            # 'cumulative_test_count': 'kumulativni_pocet_testu'
        }

        weekly_deaths_mapping = {
            'year': 'rok',
            'week_number': 'tyden',
            'date_start': 'casref_od',
            'date_end': 'casref_do',
            'death_count_1': '0-14',
            'death_count_2': '15-39',
            'death_count_3': '40-64',
            'death_count_4': '65-84',
            'death_count_5': '85+',
        }

        import_collection(self.db, 'daily_deaths', CovidDeath, deaths_mapping)
        import_collection(self.db, 'confirmed_cases', ConfirmedCase, case_mapping)
        import_collection(self.db, 'daily_tests', PerformedTests, test_mapping)
        import_collection(self.db, 'weekly_deaths', WeeklyDeaths, weekly_deaths_mapping)
        print(f"Total tests: {PerformedTests.objects.cumulative_test_count()}")
        print("Import finished")

    def get_area_cases(self):
        area_cases = {}
        query = NUTS_3_AREA.objects.annotate(case_count=Count('nuts_4_area__confirmedcase')) \
            .values('name', 'case_count')
        for area in query:
            area_cases[area['name']] = area['case_count']

        return area_cases

    def __init__(self):
        super().__init__()
        self.db_client = pymongo.MongoClient("mongodb://localhost:27017/")
        self.db = self.db_client['covid_data']
        self.action_key = None
        self.response = {}
        self.context = {}
        self.actions = {
            'populate_area_tables': self.populate_area_tables,
            'import_data': self.import_data,
            'clear_db': self.clear_db,
        }
        # print(f"Existing DBs: {db_client.list_database_names()}")

    def get_context_data(self, **kwargs):
        self.context = super().get_context_data(**kwargs)

        expr = F('death_count_1') + F('death_count_2') + F('death_count_3') + F('death_count_4') + F('death_count_5')
        week_numbers = WeeklyDeaths.objects.values('week_number')
        annotated = week_numbers.annotate(death_sums=expr)
        weekly_deaths = annotated.values('week_number', 'death_sums')
        grouped = {}
        for week_data in weekly_deaths:
            week_number = week_data['week_number']
            if week_number in grouped:
                grouped[week_number].append(week_data['death_sums'])
            else:
                grouped[week_number] = [week_data['death_sums']]

        if grouped:
            self.context['weekly_deaths'] = json.dumps(grouped)

        age_data = list(CovidDeath.objects.all().values_list('age', flat=True))
        if age_data:
            self.context['age_data'] = json.dumps(age_data)
        # age_data = list(deceased_query_set.values_list('age', flat=True))
        # json_data = serializers.serialize('json', deceased_query_set)
        # self.context['deceased_list'] = deceased_query_set[:10]
        # self.context['deceased_data'] = json_data

        area_cases = self.get_area_cases()
        if area_cases:
            self.context['area_cases'] = json.dumps(area_cases)

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


@method_decorator(never_cache, name='dispatch')
class DashboardView(generic.TemplateView):
    template_name = 'covid_app/dashbord.html'

    def __init__(self):
        super().__init__()
        self.action_key = None
        self.response = {}
        self.context = {}
        CovidOverview.objects.all().delete()
        try:
            overview = CovidOverview.objects.get(id=1)
            if overview.date < datetime.today().date():
                self.update_overview(overview)
        except CovidOverview.DoesNotExist:
            self.update_overview()

    def update_overview(self, overview=None):
        overview_json = download(url=URL_COVID_OVERVIEW).json()
        # last_update = overview_json['modified']
        overview_mapping = {
            'date': 'datum',
            'confirmed_cases': 'potvrzene_pripady_celkem',
            'confirmed_cases_yesterday': 'potvrzene_pripady_vcerejsi_den',
            'confirmed_cases_today': 'potvrzene_pripady_dnesni_den',
            'active_cases': 'aktivni_pripady',
            'total_recovered': 'vyleceni',
            'total_deaths': 'umrti',
            'hospitalized_count': 'aktualne_hospitalizovani',
            'performed_tests': 'provedene_testy_celkem',
            'performed_tests_yesterday': 'provedene_testy_vcerejsi_den',
        }

        if not overview:
            CovidOverview.objects.create(**apply_mapping(overview_mapping, overview_json['data'][0]))
        else:
            for attr, value in apply_mapping(overview_mapping, overview_json['data'][0]).items():
                setattr(overview, attr, value)
            overview.save()

    def get_context_data(self, **kwargs):
        self.context = super().get_context_data(**kwargs)
        overview = CovidOverview.objects.all().values()[0]
        overview['date'] = datetime.strftime(overview['date'], '%Y-%m-%d')
        self.context['overview_data'] = overview
        return self.context

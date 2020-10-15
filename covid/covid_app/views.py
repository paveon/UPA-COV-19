import pymongo
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.apps import apps
from django.db.models import F, Q, Count, Avg, Window, ValueRange, RowRange
from django.utils.decorators import method_decorator
from django.views import generic, View
from django.views.decorators.cache import never_cache
from datetime import datetime
from django.core.cache import cache

from .area_codes import *
from .download_utils import download
from .models import *

URL_COVID_OVERVIEW = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/zakladni-prehled.json'


def apply_mapping(mapping, document):
    object_dict = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            object_dict[key] = document[value]
        else:
            object_dict[key] = value.get('obj_cache').get(document[value.get('name')], value.get('default'))
    return object_dict


def import_collection(covid_db, collection_name, model_cls, mapping, begin_date=None, date_field_name=None):
    if collection_name not in covid_db.list_collection_names():
        return
    collection = covid_db[collection_name]
    if begin_date:
        date_filter = {date_field_name: {'$gt': datetime.combine(begin_date, datetime.min.time())}}
        cursor = collection.find(date_filter)
    else:
        cursor = collection.find({})
    objects = [model_cls(**apply_mapping(mapping, document)) for document in cursor]
    model_cls.objects.bulk_create(objects)


def get_base_layout(title, xtitle=None, ytitle=None, barmode=None, xtickvals=None, xticktext=None, ytickvals=None,
                    yticktext=None):
    return {
        'title': title,
        'titlefont': {'color': 'white'},
        'yaxis': {'title': ytitle, 'gridcolor': 'rgba(255, 255, 255, 0.75)',
                  'titlefont': {'color': 'white'}, 'tickfont': {'color': 'white'},
                  'tickvals': ytickvals, 'ticktext': yticktext,
                  },
        'xaxis': {'title': xtitle, 'gridcolor': 'rgba(255, 255, 255, 0.75)',
                  'titlefont': {'color': 'white'}, 'tickfont': {'color': 'white'},
                  'tickvals': xtickvals, 'ticktext': xticktext,
                  },
        'legend': {'font': {'color': 'white'}},
        'paper_bgcolor': 'rgb(45, 38, 38)',
        'plot_bgcolor': 'rgb(45, 38, 38)',
        # 'paper_bgcolor': 'rgb(243, 243, 243)',
        # 'plot_bgcolor': 'rgb(243, 243, 243)',
        'barmode': barmode,
    }


@method_decorator(never_cache, name='dispatch')
class StatisticsView(generic.TemplateView):
    template_name = 'covid_app/statistics.html'

    def clear_db(self):
        CovidDeath.objects.all().delete()
        ConfirmedCase.objects.all().delete()
        RecoveredPerson.objects.all().delete()
        WeeklyDeaths.objects.all().delete()
        DailyStatistics.objects.all().delete()
        cache.delete_many(self.get_actions.keys())
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

    def cache_regions(self):
        self.nuts_4_cache = {x.pk: x for x in NUTS_4_AREA.objects.all()}
        self.nuts_0_cache = {x.pk: x for x in NUTS_0_AREA.objects.all()}
        self.cz_cache = self.nuts_0_cache['CZ']

        self.deaths_mapping = {
            'date_of_death': 'datum',
            'age': 'vek',
            'gender': 'pohlavi',
            'nuts_4_area': {'name': 'okres_lau_kod', 'obj_cache': self.nuts_4_cache}
        }

        self.case_mapping = {
            'report_date': 'datum',
            'age': 'vek',
            'gender': 'pohlavi',
            'nuts_4_area': {'name': 'okres_lau_kod', 'obj_cache': self.nuts_4_cache},
            'origin_country': {'name': 'nakaza_zeme_csu_kod', 'obj_cache': self.nuts_0_cache, 'default': self.cz_cache}
        }

        self.recovered_mapping = {
            'date': 'datum',
            'age': 'vek',
            'gender': 'pohlavi',
            'nuts_4_area': {'name': 'okres_lau_kod', 'obj_cache': self.nuts_4_cache}
        }

        self.weekly_deaths_mapping = {
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

        self.daily_stats_mapping = {
            'date': 'datum',
            'test_count': 'prirustkovy_pocet_testu',
            'confirmed_case_count': 'prirustkovy_pocet_nakazenych',
            'recovered_cumulative': 'kumulativni_pocet_vylecenych',
            'deaths_cumulative': 'kumulativni_pocet_umrti'
        }

    def update_data(self):
        self.cache_regions()
        models_to_update = [
            ['covid_deaths', CovidDeath, self.deaths_mapping, 'date_of_death', 'datum'],
            ['rho_confirmed_cases', ConfirmedCase, self.case_mapping, 'report_date', 'datum'],
            ['rho_recovered_persons', RecoveredPerson, self.recovered_mapping, 'date', 'datum'],
            ['weekly_deaths', WeeklyDeaths, self.weekly_deaths_mapping, 'date_end', 'casref_od'],
            ['daily_statistics', DailyStatistics, self.daily_stats_mapping, 'date', 'datum'],
        ]

        for arg_list in models_to_update:
            model_cls = arg_list[1]
            try:
                arg_list[-2] = getattr(model_cls.objects.latest(arg_list[-2]), arg_list[-2])
                import_collection(self.db, *arg_list)
            except model_cls.DoesNotExist:
                import_collection(self.db, *arg_list[:-2])

    def import_data(self):
        self.clear_db()

        if not NUTS_0_AREA.objects.exists() \
                or not NUTS_1_AREA.objects.exists() \
                or not NUTS_2_AREA.objects.exists() \
                or not NUTS_3_AREA.objects.exists() \
                or not NUTS_4_AREA.objects.exists():
            self.populate_area_tables()

        self.cache_regions()

        import_collection(self.db, 'covid_deaths', CovidDeath, self.deaths_mapping)
        import_collection(self.db, 'rho_confirmed_cases', ConfirmedCase, self.case_mapping)
        import_collection(self.db, 'rho_recovered_persons', RecoveredPerson, self.recovered_mapping)
        import_collection(self.db, 'weekly_deaths', WeeklyDeaths, self.weekly_deaths_mapping)
        import_collection(self.db, 'daily_statistics', DailyStatistics, self.daily_stats_mapping)
        print("Import finished")

    def __init__(self):
        super().__init__()
        self.db_client = pymongo.MongoClient("mongodb://localhost:27017/")
        self.db = self.db_client['covid_data']
        self.action_key = None
        self.request = None
        self.response = {}
        self.context = {}

        self.nuts_4_cache = None
        self.nuts_0_cache = None
        self.cz_cache = None

        self.deaths_mapping = None
        self.case_mapping = None
        self.weekly_deaths_mapping = None
        self.daily_stats_mapping = None
        self.recovered_mapping = None

        self.post_actions = {
            'populate_area_tables': self.populate_area_tables,
            'import_data': self.import_data,
            'update_data': self.update_data,
            'clear_db': self.clear_db,
        }
        self.get_actions = {
            'get_age_distribution': self.get_case_age_distribution,
            'get_area_cases': self.get_cases_by_area,
            'get_age_average_evolution': self.get_age_average_evolution,
            'get_death_age_data': self.get_death_age_data,
        }
        # print(f"Existing DBs: {db_client.list_database_names()}")

    def get_death_age_data(self):
        age_data = list(CovidDeath.objects.all().values_list('age', flat=True))
        graph_data = [{
            'y': age_data,
            'type': 'box',
            'name': 'Age at death'
        }]
        graph_layout = get_base_layout('Age of Dead Patients for COVID-19')
        graph_layout['showlegend'] = False
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_cases_by_area(self):
        area_cases = {}
        q_object = ~Q(code='CZ999') & ~Q(code='CZZZZ')  # Ignore extra region and unknown region
        query = NUTS_3_AREA.objects.filter(q_object).annotate(case_count=Count('nuts_4_area__confirmedcase')) \
            .values('name', 'case_count')
        for area in query:
            area_cases[area['name']] = area['case_count']

        graph_data = [{
            'x': list(area_cases.keys()),
            'y': list(area_cases.values()),
            'type': 'bar',
            'name': 'Region Case Counts'
        }]

        graph_layout = get_base_layout('Region Counts of COVID-19 Cases Confirmed by Regional Hygiene Office',
                                       xtitle='Region', ytitle='Number of Cases')
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_case_age_distribution(self):
        age_distribution = cache.get(self.request.GET['action'])
        # age_distribution = None
        if age_distribution:
            male_counts = age_distribution['male_counts']
            female_counts = age_distribution['female_counts']
            case_counts_evolution = age_distribution['case_counts_evolution']
        else:
            male_cases = ConfirmedCase.objects.filter(gender='M')
            female_cases = ConfirmedCase.objects.filter(gender='Z')

            age_categories = {}
            age_windows = {}
            age_windows_incr = {}
            for lower_bound in range(0, 100, 10):
                q_object = Q(age__gte=lower_bound) & Q(age__lt=lower_bound + 10)
                age_categories[f"age{lower_bound}"] = Count('age', filter=q_object)
                age_windows[f"cumulative_{lower_bound}"] = Window(
                    expression=Count('age', filter=q_object),
                    order_by=F('report_date').asc()
                )
                age_windows_incr[f"incremental_{lower_bound}"] = Window(
                    expression=Count('age', filter=q_object),
                    partition_by=[F'report_date'],
                    order_by=F('report_date').asc()
                )

            # ConfirmedCase.objects.filter(Q(age__gte=20) & Q(age__lte=30) & Q(report_date__lte=datetime(2020, 3, 6).date())).count()
            case_counts_in_time = list(ConfirmedCase.objects.annotate(**age_windows, **age_windows_incr)
                                       .values_list('report_date', *age_windows.keys(), *age_windows_incr.keys())
                                       .distinct())

            # Transpose list of lists (columns -> rows)
            case_counts_evolution = list(map(list, zip(*case_counts_in_time)))

            male_counts = list(male_cases.aggregate(**age_categories).values())
            female_counts = list(female_cases.aggregate(**age_categories).values())
            cache.set(self.request.GET['action'], {
                'male_counts': male_counts,
                'female_counts': female_counts,
                'case_counts_evolution': case_counts_evolution
            })

        age_labels = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-89', '90-99']

        view_id = int(self.request.GET['graphViewID'])
        if view_id < 2:
            age_categories = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
            graph_layout = get_base_layout('Age Distribution of Confirmed COVID-19 Cases', barmode='overlay',
                                           xtitle='Number of COVID-19 cases', ytitle='Age')
            graph_layout['bargap'] = 0.1
            graph_data = [{
                'y': age_categories,
                'x': male_counts,
                'orientation': 'h',
                'name': 'Men',
                'hoverinfo': 'x',
                'type': 'bar',
            }, {
                'y': age_categories,
                'x': [-x for x in female_counts],
                'orientation': 'h',
                'name': 'Women',
                'text': female_counts,
                'hoverinfo': 'text',
                'type': 'bar',
            }]
            if view_id == 1:
                graph_layout['yaxis'], graph_layout['xaxis'] = graph_layout['xaxis'], graph_layout['yaxis']
                graph_layout['barmode'] = 'stack'
                graph_data[0]['x'] = graph_data[1]['x'] = age_categories
                graph_data[0]['hoverinfo'] = 'y'
                graph_data[0]['orientation'] = graph_data[1]['orientation'] = 'v'
                graph_data[0]['y'] = male_counts
                graph_data[1]['y'] = female_counts

        else:
            if view_id == 2:
                title = "Confirmed Cases - Daily Change"
                data = case_counts_evolution[11:]
            else:
                title = "Confirmed Cases - Cumulative"
                data = case_counts_evolution[1:11]

            graph_layout = get_base_layout(title, barmode='overlay',
                                           xtitle='Date', ytitle='Number of Cases')
            graph_data = []
            for age_label, age_category in zip(age_labels, data):
                graph_data.append({
                    'type': 'scatter',
                    'x': case_counts_evolution[0],
                    'y': age_category,
                    'mode': 'lines',
                    'name': age_label
                })

        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_age_average_evolution(self):
        # cached_data = cache.get(self.request.GET['action'])
        cached_data = None
        if cached_data:
            dates = cached_data['dates']
            averages = cached_data['averages']
        else:
            averages_queryset = ConfirmedCase.objects.annotate(
                moving_age_avg=Window(
                    expression=Avg('age'),
                    # partition_by=[F('report_date')],
                    order_by=F('report_date').asc(),
                )
            ).values('report_date', 'moving_age_avg').distinct()

            dates = []
            averages = []
            for day in averages_queryset:
                dates.append(day['report_date'])
                averages.append(day['moving_age_avg'])

            cache.set(self.request.GET['action'], {
                'dates': dates,
                'averages': averages
            })

        graph_data = [{
            'type': 'scatter',
            'x': dates,
            'y': averages,
            'mode': 'lines',
        }]
        graph_layout = get_base_layout('Age Average Evolution of COVID-19 Cases', barmode='overlay',
                                       xtitle='Date', ytitle='Average Age to Date')
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_context_data(self, **kwargs):
        self.context = super().get_context_data(**kwargs)

        # count1 = DailyStatistics.objects.death_count(datetime.today() - timedelta(days=10))
        # count2 = CovidDeath.objects.death_count(datetime.today() - timedelta(days=10))

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

        return self.context

    def get(self, request, *args, **kwargs):
        self.request = request
        if self.request.is_ajax():
            self.action_key = self.request.GET['action']
            action = self.get_actions[self.action_key]
            json_data = action()
            return JsonResponse(json_data)
        else:
            self.context = self.get_context_data(**kwargs)
            return render(self.request, self.template_name, self.context)

    def post(self, request, *args, **kwargs):
        self.context = self.get_context_data(**kwargs)
        self.action_key = request.POST['action']
        action = self.post_actions[self.action_key]
        if request.is_ajax():
            action()
            return JsonResponse(self.response)

        action()
        return render(request, self.template_name, self.context)


@method_decorator(never_cache, name='dispatch')
class DashboardView(generic.TemplateView):
    template_name = 'covid_app/dashboard.html'

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
        overview_data = overview_json['data'][0]
        overview_data['datum'] = overview_json['modified']
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

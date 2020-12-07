import pymongo
import json

from itertools import islice
from django.shortcuts import render
from django.http import JsonResponse
from django.apps import apps
from django.db.models import F, Q, Count, Avg, Window, ValueRange, RowRange
from django.db.models.functions import ExtractWeek, ExtractYear
from django.utils.decorators import method_decorator
from django.views import generic, View
from django.views.decorators.cache import never_cache
from datetime import datetime
from django.urls import reverse
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
    print(f"Importing collection '{collection_name}'")
    if collection_name not in covid_db.list_collection_names():
        return

    collection = covid_db[collection_name]
    if begin_date:
        date_filter = {date_field_name: {'$gt': datetime.combine(begin_date, datetime.min.time())}}
        cursor = collection.find(date_filter)
    else:
        cursor = collection.find({})

    print(f"    Creating '{model_cls.__name__}' objects")
    objects = [model_cls(**apply_mapping(mapping, document)) for document in cursor]
    print(f"    Inserting '{len(objects)}' objects into the database")

    def chunker(seq, chunk_size):
        for pos in range(0, len(seq), chunk_size):
            yield seq[pos:pos + chunk_size]

    batch_idx = 0
    batch_size = 10000
    for object_batch in chunker(objects, batch_size):
        print(f"    [{batch_idx * batch_size} - {(batch_idx * batch_size) + len(object_batch)}]")
        model_cls.objects.bulk_create(object_batch, batch_size)
        batch_idx += 1


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

        if (not NUTS_0_AREA.objects.exists()
                or not NUTS_1_AREA.objects.exists()
                or not NUTS_2_AREA.objects.exists()
                or not NUTS_3_AREA.objects.exists()
                or not NUTS_4_AREA.objects.exists()):
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
            'get_area_deaths': self.get_deaths_by_area,
            'get_state_cases': self.get_cases_by_state,
            'get_daily_statistics': self.get_daily_statistics,
            'get_age_average_evolution': self.get_age_average_evolution,
            'get_death_age_data': self.get_death_age_data,
            'get_weekly_deaths': self.get_weekly_deaths,
            'get_impact_covid': self.get_impact_covid,
            'get_weekly_deaths_history': self.get_weekly_deaths_history,
            'get_comparison_covid_deaths': self.get_comparison_covid_deaths,
        }

    def from_cache_or_compute(self, compute_func, view_id):
        action_name = self.request.GET['action']
        view_cache = cache.get(action_name, {})
        graph_view_cache = view_cache.get(view_id)
        if graph_view_cache:
            return graph_view_cache

        data = compute_func()
        view_cache[view_id] = data
        cache.set(action_name, view_cache)
        return data

    def get_weekly_deaths(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            expr = (F('death_count_1') + F('death_count_2') + F('death_count_3') +
                    F('death_count_4') + F('death_count_5'))
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

            return list(grouped.values())

        weekly_deaths_data = self.from_cache_or_compute(compute, view_id)
        if not weekly_deaths_data:
            weekly_deaths_data = [[]] * 52

        # Ignore transition week 53
        graph_data = []
        for i in range(0, 52):
            graph_data.append({
                'y': weekly_deaths_data[i],
                'type': 'box',
                'name': f"Week {i + 1}"
            })
        graph_layout = get_base_layout('Weekly Deaths Data Summarization from 2011 to Present')
        graph_layout['showlegend'] = False
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_weekly_deaths_history(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            expr = (F('death_count_1') + F('death_count_2') + F('death_count_3') +
                    F('death_count_4') + F('death_count_5'))

            weekly_deaths_history_query = (WeeklyDeaths.objects.values('week_number')
                                           .filter(Q(year=2011))
                                           .annotate(death_sums=expr)
                                           .values_list('week_number', 'death_sums'))

            weekly_deaths_2019_query = (WeeklyDeaths.objects.values('week_number')
                                        .filter(Q(year=2019))
                                        .annotate(death_sums=expr)
                                        .values_list('week_number', 'death_sums'))

            weekly_deaths_2020_query = (WeeklyDeaths.objects.values('week_number')
                                        .filter(Q(year=2020))
                                        .annotate(death_sums=expr)
                                        .values_list('week_number', 'death_sums'))

            return (list(map(list, zip(*weekly_deaths_history_query))),
                    list(map(list, zip(*weekly_deaths_2019_query))),
                    list(map(list, zip(*weekly_deaths_2020_query))))

        weekly_deaths_history, weekly_deaths_2019, weekly_deaths_2020 = self.from_cache_or_compute(compute, view_id)
        if not weekly_deaths_history:
            weekly_deaths_history = [[], []]
        if not weekly_deaths_2019:
            weekly_deaths_2019 = [[], []]
        if not weekly_deaths_2020:
            weekly_deaths_2020 = [[], []]

        graph_data = [
            {
                'x': weekly_deaths_history[0],
                'y': weekly_deaths_history[1],
                'type': 'line',
                'name': '2011'
            },
            {
                'x': weekly_deaths_2019[0],
                'y': weekly_deaths_2019[1],
                'type': 'line',
                'name': '2019'
            },
            {
                'x': weekly_deaths_2020[0],
                'y': weekly_deaths_2020[1],
                'type': 'line',
                'name': '2020 (year of pandemic)'
            }
        ]

        graph_layout = get_base_layout('Comparision of Weekly Deaths for 2011, 2019 and 2020 (year of pandemic)',
                                       xtitle='Week of Year', ytitle='Number of Deaths for Week')
        graph_layout['showlegend'] = True
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_comparison_covid_deaths(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            expr = (F('death_count_1') + F('death_count_2') + F('death_count_3') +
                    F('death_count_4') + F('death_count_5'))

            if WeeklyDeaths.objects.exists():
                total_deaths = (WeeklyDeaths.objects.values('week_number')
                                .filter(Q(year=2020))
                                .annotate(death_sums=expr)
                                .aggregate(Sum('death_sums'))
                                .get("death_sums__sum", 0))
            else:
                total_deaths = 0

            if CovidOverview.objects.exists():
                covid_deaths = (CovidOverview.objects.values('total_deaths')
                                .aggregate(Sum('total_deaths'))
                                .get("total_deaths__sum", 0))
            else:
                covid_deaths = 0

            return total_deaths, covid_deaths

        total_deaths_2020, total_covid_deaths = self.from_cache_or_compute(compute, view_id)
        deaths_not_covid = total_deaths_2020 - total_covid_deaths

        graph_data = [
            {
                'labels': ["Deaths to COVID-19", "Other Deaths"],
                'values': [total_covid_deaths, deaths_not_covid],
                'type': 'pie',
            }
        ]

        graph_layout = get_base_layout('Proportion of COVID-19 Deaths to All Deaths in 2020 for the Czech Republic')
        graph_layout['showlegend'] = True
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_death_age_data(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            return list(CovidDeath.objects.all().values_list('age', flat=True))

        age_data = self.from_cache_or_compute(compute, view_id)

        graph_data = [{
            'y': age_data,
            'type': 'box',
            'name': 'Age at death'
        }]
        graph_layout = get_base_layout('Age of Dead Patients for COVID-19')
        graph_layout['showlegend'] = False
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_impact_covid(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute_cases():
            if view_id == 0:
                annotations = {
                    'confirmed_case_count': Window(expression=Count('report_date'), order_by=F('report_date').asc())
                }
                selected_values = ['report_date', 'confirmed_case_count']
                conf_cases = ConfirmedCase.objects.annotate(**annotations).values_list(*selected_values).distinct()
                return list(map(list, zip(*conf_cases)))

            elif view_id == 1 or view_id == 2:
                conf_cases = DailyStatistics.objects.values_list('date', 'confirmed_case_count')
                return list(map(list, zip(*conf_cases)))

        def compute_deaths():
            if view_id == 0:
                daily_deaths = DailyStatistics.objects.values_list('date', 'deaths_cumulative')
                return list(map(list, zip(*daily_deaths)))

            elif view_id == 1 or view_id == 2:
                daily_deaths = (CovidDeath.objects.order_by('date_of_death')
                                .values_list('date_of_death')
                                .annotate(Count('date_of_death')))
                return list(map(list, zip(*daily_deaths)))

        def compute_impact():
            if view_id == 0:
                annotations = {
                    'confirmed_case_count': Window(expression=Count('report_date'), order_by=F('report_date').asc())}
                selected_values = ['report_date', 'confirmed_case_count']
                conf_cases = ConfirmedCase.objects.annotate(**annotations).values_list(*selected_values).distinct()
                daily_deaths = DailyStatistics.objects.values_list('date', 'deaths_cumulative')

            elif view_id == 1 or view_id == 2:
                daily_deaths = CovidDeath.objects.order_by('date_of_death').values_list('date_of_death').annotate(
                    Count('date_of_death'))
                conf_cases = DailyStatistics.objects.values_list('date', 'confirmed_case_count')

            annotations = []
            for cases in conf_cases:
                date_from_case = cases[0]
                if (view_id == 1 or view_id == 2) and daily_deaths.filter(date_of_death=date_from_case):
                    query_deaths = list(daily_deaths.filter(date_of_death=date_from_case))
                    count_impact = query_deaths[0][1] / cases[1]
                    annotations.append([cases[0], count_impact])
                elif view_id == 0 and daily_deaths.filter(date=date_from_case):
                    query_deaths = list(daily_deaths.filter(date=date_from_case))
                    count_impact = query_deaths[0][1] / cases[1]
                    annotations.append([cases[0], count_impact])
                else:
                    annotations.append([cases[0], 0])

            return list(map(list, zip(*annotations)))

        death_stat = compute_deaths()
        if not death_stat:
            death_stat = [[], []]

        test_statistics = compute_cases()
        if not test_statistics:
            test_statistics = [[], []]

        impact_covid = self.from_cache_or_compute(compute_impact, view_id)
        if not impact_covid:
            impact_covid = [[], []]

        graph_layouts = {
            0: get_base_layout('Cumulative Impact of Covid', barmode='overlay',
                               xtitle='Date', ytitle='Number'),
            1: get_base_layout('Number of Cases and Deaths per day', barmode='overlay',
                               xtitle='Date', ytitle='Number'),
            2: get_base_layout('Ratio of Daily Deaths and Daily Cases (Daily Deaths / Daily Cases)', barmode='overlay',
                               xtitle='Date', ytitle='Number'),
        }

        if view_id == 2:
            graph_data = [{
                'x': impact_covid[0],
                'y': impact_covid[1],
                'type': 'line',
                'name': 'Impact'
            }]

            return {'graph_layout': graph_layouts[view_id], 'graph_data': graph_data}

        graph_data = [
            {
                'x': test_statistics[0],
                'y': test_statistics[1],
                'type': 'line',
                'name': 'Cases'
            },
            {
                'x': death_stat[0],
                'y': death_stat[1],
                'type': 'line',
                'name': 'Deaths'
            }
        ]
        return {'graph_layout': graph_layouts[view_id], 'graph_data': graph_data}

    def get_cases_by_area(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            q_object = ~Q(code='CZ999') & ~Q(code='CZZZZ')  # Ignore extra region and unknown region
            area_cases_query = (NUTS_3_AREA.objects.filter(q_object)
                                .annotate(case_count=Count('nuts_4_area__confirmedcase'))
                                .values_list('name', 'case_count'))

            return list(map(list, zip(*area_cases_query)))

        area_cases = self.from_cache_or_compute(compute, view_id)

        graph_data = []
        if view_id == 0:
            graph_data = [{
                'x': area_cases[0],
                'y': area_cases[1],
                'type': 'bar',
                'name': 'Region Case Counts'
            }]

        if view_id == 1:
            graph_data = [{
                'labels': area_cases[0],
                'values': area_cases[1],
                'type': 'pie',
                'name': 'Region Case Counts'
            }]

        graph_layout = get_base_layout('Region Counts of COVID-19 Cases Confirmed by Regional Hygiene Office',
                                       xtitle='Region', ytitle='Number of Cases')
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_deaths_by_area(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            q_object = ~Q(code='CZ999') & ~Q(code='CZZZZ')  # Ignore extra region and unknown region
            area_deaths_query = (
                NUTS_3_AREA.objects.filter(q_object).annotate(death_count=Count('nuts_4_area__coviddeath')).values_list(
                    'name', 'death_count'))

            return list(map(list, zip(*area_deaths_query)))

        area_deaths = self.from_cache_or_compute(compute, view_id)

        graph_data = []
        if view_id == 0:
            graph_data = [{
                'x': area_deaths[0],
                'y': area_deaths[1],
                'type': 'bar',
                'name': 'Region Death Counts'
            }]

        if view_id == 1:
            graph_data = [{
                'labels': area_deaths[0],
                'values': area_deaths[1],
                'type': 'pie',
                'name': 'Region Death Counts'
            }]

        graph_layout = get_base_layout('Region Counts of COVID-19 Deaths',
                                       xtitle='Region', ytitle='Number of Deaths')
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_cases_by_state(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            q_object = ~Q(code='CZ')  # Ignore Czech Republic
            state_cases_query = NUTS_0_AREA.objects.filter(q_object).annotate(
                case_count=Count('confirmedcase')).order_by('-case_count').values_list('name', 'case_count')

            return list(map(list, zip(*state_cases_query)))

        state_cases = self.from_cache_or_compute(compute, view_id)

        # in both graphs ignore foreign states with no confirmed Czech inhabitans
        graph_data = []
        graph_layout = {}
        if view_id == 0:

            graph_data = [{
                'x': state_cases[0],
                'y': state_cases[1],
                'type': 'bar',
                'transforms': [{
                    'type': 'filter',
                    'target': 'y',
                    'operation': '>',
                    'value': 0
                }],
                'name': 'State Case Counts'
            }]
            graph_layout = get_base_layout('COVID-19 Cases Confirmed for Czech Inhabitans in Abroad',
                                           ytitle='Number of Cases')

        elif view_id == 1:
            graph_data = [{
                'labels': state_cases[0],
                'values': state_cases[1],
                'type': 'pie',
                'transforms': [{
                    'type': 'filter',
                    'target': 'values',
                    'operation': '>',
                    'value': 49
                }],
                'name': 'Top State Case Counts'
            }]

            graph_layout = get_base_layout('Foreign States With At Least 50 Confirmed Czech Inhabitans', xtitle='State',
                                           ytitle='Number of Cases')

        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_daily_statistics(self):
        view_id = int(self.request.GET['graphViewID'])

        graph_data = []
        graph_layout = {}
        if view_id == 0:
            def compute():
                testing_query = DailyStatistics.objects.values_list('date', 'test_count')
                return list(map(list, zip(*testing_query)))

            test_statistics = self.from_cache_or_compute(compute, view_id)
            if not test_statistics:
                test_statistics = [[], []]

            graph_data = [{
                'x': test_statistics[0],
                'y': test_statistics[1],
                'type': 'line',
                'name': 'Development of Performed Tests'
            }]

            graph_layout = get_base_layout('Development of Performed COVID-19 Tests', xtitle='Date',
                                           ytitle='Number of Tests')

        if view_id == 1:
            def compute():
                recovered_cases_query = DailyStatistics.objects.values_list('date', 'recovered_cumulative')
                return list(map(list, zip(*recovered_cases_query)))

            recovered_cases = self.from_cache_or_compute(compute, view_id)
            if not recovered_cases:
                recovered_cases.append([])
                recovered_cases.append([])

            graph_data = [{
                'x': recovered_cases[0],
                'y': recovered_cases[1],
                'type': 'line',
                'name': 'Development of Recovered Cases'
            }]

            graph_layout = get_base_layout('Development of COVID-19 Recovered Cases', xtitle='Date',
                                           ytitle='Cumulative Number of Recovered Cases')
        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_case_age_distribution(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            if view_id < 2:
                query_age_categories = {}
                male_cases = ConfirmedCase.objects.filter(gender='M')
                female_cases = ConfirmedCase.objects.filter(gender='Z')
                for lower_bound in range(0, 100, 10):
                    q_object = Q(age__gte=lower_bound) & Q(age__lt=lower_bound + 10)
                    query_age_categories[f"age{lower_bound}"] = Count('age', filter=q_object)

                return {'male': list(male_cases.aggregate(**query_age_categories).values()),
                        'female': list(female_cases.aggregate(**query_age_categories).values())}

            else:
                partition_fields = [F'report_date'] if view_id == 2 else None
                age_windows = {}
                for lower_bound in range(0, 100, 10):
                    q_object = Q(age__gte=lower_bound) & Q(age__lt=lower_bound + 10)
                    age_windows[f"{lower_bound}"] = Window(
                        expression=Count('age', filter=q_object),
                        partition_by=partition_fields,
                        order_by=F('report_date').asc()
                    )
                timeline_data = (ConfirmedCase.objects.annotate(**age_windows)
                                 .values_list('report_date', *age_windows.keys())
                                 .distinct())

                return list(map(list, zip(*timeline_data)))

        data = self.from_cache_or_compute(compute, view_id)
        age_labels = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-89', '90-99']

        if view_id < 2:
            age_categories = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
            graph_layout = get_base_layout('Age Distribution of Confirmed COVID-19 Cases', barmode='overlay',
                                           xtitle='Number of COVID-19 cases', ytitle='Age')
            graph_layout['bargap'] = 0.1
            graph_data = [{
                'y': age_categories,
                'x': data['male'],
                'orientation': 'h',
                'name': 'Men',
                'hoverinfo': 'x',
                'type': 'bar',
            }, {
                'y': age_categories,
                'x': [-x for x in data['female']],
                'orientation': 'h',
                'name': 'Women',
                'text': data['female'],
                'hoverinfo': 'text',
                'type': 'bar',
            }]
            if view_id == 1:
                graph_layout['yaxis'], graph_layout['xaxis'] = graph_layout['xaxis'], graph_layout['yaxis']
                graph_layout['barmode'] = 'stack'
                graph_data[0]['x'] = graph_data[1]['x'] = age_categories
                graph_data[0]['hoverinfo'] = 'y'
                graph_data[0]['orientation'] = graph_data[1]['orientation'] = 'v'
                graph_data[0]['y'] = data['male']
                graph_data[1]['y'] = data['female']

        else:
            title = "Confirmed Cases - Daily Change" if view_id == 2 else "Confirmed Cases - Cumulative"
            graph_layout = get_base_layout(title, barmode='overlay', xtitle='Date', ytitle='Number of Cases')
            graph_data = []
            for age_label, age_category in zip(age_labels, data[1:]):
                graph_data.append({
                    'type': 'scatter',
                    'x': data[0],
                    'y': age_category,
                    'mode': 'lines',
                    'name': age_label
                })

        return {'graph_layout': graph_layout, 'graph_data': graph_data}

    def get_age_average_evolution(self):
        view_id = int(self.request.GET['graphViewID'])

        def compute():
            if view_id == 0:
                annotations = {'cumulative_age_avg': Window(expression=Avg('age'), order_by=F('report_date').asc())}
                selected_values = ['report_date', 'cumulative_age_avg']
            elif view_id == 1:
                annotations = {
                    'year': ExtractYear('report_date'),
                    'week': ExtractWeek('report_date'),
                    'weekly_age_avg': Window(expression=Avg('age'),
                                             partition_by=[F('week'), F('year')],
                                             order_by=F('week').asc())
                }
                selected_values = ['week', 'weekly_age_avg']
            else:
                annotations = {
                    'daily_age_avg': Window(expression=Avg('age'),
                                            partition_by=[F('report_date')],
                                            order_by=F('report_date').asc())
                }
                selected_values = ['report_date', 'daily_age_avg']

            queryset = ConfirmedCase.objects.annotate(**annotations).values_list(*selected_values).distinct()
            return list(map(list, zip(*queryset)))

        data = self.from_cache_or_compute(compute, view_id)

        layouts = {
            0: get_base_layout('Cumulative Age Averages of COVID-19 Cases', barmode='overlay', xtitle='Date',
                               ytitle='Cumulative Average'),
            1: get_base_layout('Weekly Age Averages of COVID-19 Cases', barmode='overlay',
                               xtitle='Week', ytitle='Weekly Average'),
            2: get_base_layout('Daily Age Averages of COVID-19 Cases', barmode='overlay',
                               xtitle='Date', ytitle='Daily Average')
        }

        graph_data = [{
            'x': data[0],
            'y': data[1],
            'type': 'scatter',
            'mode': 'lines',
        }]
        return {'graph_layout': layouts[view_id], 'graph_data': graph_data}

    def get_context_data(self, **kwargs):
        self.context = super().get_context_data(**kwargs)

        graph_divs = {
            'cases_age_distribution_graph': {
                'tabs': ['Pyramid View', 'Stacked Bar View'],
                'action': 'get_age_distribution',
            },
            'area_cases_graph': {
                'tabs': ['Bar View', 'Pie View'],
                'action': 'get_area_cases',
            },
            'area_deaths_graph': {
                'tabs': ['Bar View', 'Pie View'],
                'action': 'get_area_deaths',
            },
            'state_cases_graph': {
                'tabs': ['Bar View', 'Pie View'],
                'action': 'get_state_cases',
            },
            'daily_statistics_graph': {
                'tabs': ['Line View', 'Line View'],
                'action': 'get_daily_statistics',
            },
            'deaths_age_graph': {
                'tabs': ['Box View'],
                'action': 'get_death_age_data',
            },
            'weekly_deaths_graph': {
                'tabs': ['Box View'],
                'action': 'get_weekly_deaths',
            },
            'get_deaths_graph_history': {
                'tabs': ['Line View'],
                'action': 'get_weekly_deaths_history',
            },
            'impact_covid': {
                'tabs': ['    ', 'Line View', 'Line View'],
                'action': 'get_impact_covid',
            },
            'get_comparison_covid_deaths': {
                'tabs': ['Pie View'],
                'action': 'get_comparison_covid_deaths',
            },
        }
        self.context['graph_divs'] = graph_divs
        self.context['action_url'] = self.request.path_info

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

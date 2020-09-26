import pymongo
from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
from covid_app.models import *


NUTS_CODES_DICT = {
    'CZ': 'Česká republika',
    'CZ0': 'Česká republika',
    'CZZ': 'Extra-Regio',
    'CZZZZ': 'Extra-Regio',
    'CZZZ': 'Extra-Regio',
    'CZ010': 'Hlavní město Praha',
    'CZ031': 'Jihočeský kraj',
    'CZ064': 'Jihomoravský kraj',
    'CZ06': 'Jihovýchod',
    'CZ03': 'Jihozápad',
    'CZ041': 'Karlovarský kraj',
    'CZ052': 'Královéhradecký kraj',
    'CZ051': 'Liberecký kraj',
    'CZ08': 'Moravskoslezsko',
    'CZ080': 'Moravskoslezský kraj',
    'CZ071': 'Olomoucký kraj',
    'CZ053': 'Pardubický kraj',
    'CZ032': 'Plzeňský kraj',
    'CZ01': 'Praha',
    'CZ05': 'Severovýchod',
    'CZ04': 'Severozápad',
    'CZ02': 'Střední Čechy',
    'CZ07': 'Střední Morava',
    'CZ020': 'Středočeský kraj',
    'CZ042': 'Ústecký kraj',
    'CZ063': 'Vysočina',
    'CZ072': 'Zlínský kraj'
}

LAU_CODES_DICT = {
    'CZ0201': 'Benešov',
    'CZ0202': 'Beroun',
    'CZ0641': 'Blansko',
    'CZ0642': 'Brno-město',
    'CZ0643': 'Brno-venkov',
    'CZ0801': 'Bruntál',
    'CZ0644': 'Břeclav',
    'CZ0411': 'Cheb',
    'CZ0422': 'Chomutov',
    'CZ0531': 'Chrudim',
    'CZ0321': 'Domažlice',
    'CZ0421': 'Děčín',
    'CZ0802': 'Frýdek-Místek',
    'CZ0631': 'Havlíčkův Brod',
    'CZ0100': 'Hlavní město Praha',
    'CZ0645': 'Hodonín',
    'CZ0521': 'Hradec Králové',
    'CZ0512': 'Jablonec nad Nisou',
    'CZ0711': 'Jeseník',
    'CZ0632': 'Jihlava',
    'CZ0313': 'Jindřichův Hradec',
    'CZ0522': 'Jičín',
    'CZ0412': 'Karlovy Vary',
    'CZ0803': 'Karviná',
    'CZ0203': 'Kladno',
    'CZ0322': 'Klatovy',
    'CZ0204': 'Kolín',
    'CZ0721': 'Kroměříž',
    'CZ0205': 'Kutná Hora',
    'CZ0513': 'Liberec',
    'CZ0423': 'Litoměřice',
    'CZ0424': 'Louny',
    'CZ0207': 'Mladá Boleslav',
    'CZ0425': 'Most',
    'CZ0206': 'Mělník',
    'CZ0804': 'Nový Jičín',
    'CZ0208': 'Nymburk',
    'CZ0523': 'Náchod',
    'CZ0712': 'Olomouc',
    'CZ0805': 'Opava',
    'CZ0806': 'Ostrava-město',
    'CZ0532': 'Pardubice',
    'CZ0633': 'Pelhřimov',
    'CZ0324': 'Plzeň-jih',
    'CZ0323': 'Plzeň-město',
    'CZ0325': 'Plzeň-sever',
    'CZ0315': 'Prachatice',
    'CZ0209': 'Praha-východ',
    'CZ020A': 'Praha-západ',
    'CZ0713': 'Prostějov',
    'CZ0314': 'Písek',
    'CZ0714': 'Přerov',
    'CZ020B': 'Příbram',
    'CZ020C': 'Rakovník',
    'CZ0326': 'Rokycany',
    'CZ0524': 'Rychnov nad Kněžnou',
    'CZ0514': 'Semily',
    'CZ0413': 'Sokolov',
    'CZ0316': 'Strakonice',
    'CZ0533': 'Svitavy',
    'CZ0327': 'Tachov',
    'CZ0426': 'Teplice',
    'CZ0525': 'Trutnov',
    'CZ0317': 'Tábor',
    'CZ0634': 'Třebíč',
    'CZ0722': 'Uherské Hradiště',
    'CZ0723': 'Vsetín',
    'CZ0646': 'Vyškov',
    'CZ0724': 'Zlín',
    'CZ0647': 'Znojmo',
    'CZ0715': 'Šumperk',
    'CZ0635': 'Žďár nad Sázavou',
    'CZ0511': 'Česká Lípa',
    'CZ0311': 'České Budějovice',
    'CZ0312': 'Český Krumlov',
    'CZ0427': 'Ústí nad Labem',
    'CZ0534': 'Ústí nad Orlicí'
}


def index(request):
    if request.is_ajax():
        print("Python import code")
        for nuts_code, region_name in NUTS_CODES_DICT.items():
            region = Region.objects.create(pk=nuts_code, name=region_name)

        for lau_code, county_name in LAU_CODES_DICT.items():
            region = County.objects.create(pk=lau_code, name=county_name)

        db_client = pymongo.MongoClient("mongodb://localhost:27017/")
        print(f"Existing DBs: {db_client.list_database_names()}")
        covid_db = db_client['covid_data']
        if 'daily_deaths' in covid_db.list_collection_names():
            deaths_collection = covid_db['daily_deaths']
            cursor = deaths_collection.find({})
            print(deaths_collection.estimated_document_count())
            for document in cursor:
                pass

        return render(request, 'covid_app/index.html', {'data': 'test'})

    else:
        return render(request, 'covid_app/index.html')

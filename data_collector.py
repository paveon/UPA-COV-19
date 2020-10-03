import pymongo
import requests
import requests.exceptions as exceptions
from datetime import *

URL_COVID_CONFIRMED_CASES = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/osoby.json'
URL_COVID_DEATHS = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/umrti.json'
URL_COVID_TESTS = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/testy.json'
URL_WEEKLY_DEATHS = 'https://www.czso.cz/documents/62353418/138258837/130185-20data092920.csv'


def download_file(url, output_path=None):
    data = requests.get(url, timeout=10)
    data.raise_for_status()
    if data.status_code != 200:
        raise exceptions.ConnectionError()

    # This check doesn't work if the message body uses compression
    # headers = data.headers
    # content_length = headers.get('content-length')
    # if content_length is not None:
    #     content_length = int(content_length)
    #     if content_length != len(data.content):
    #         raise exceptions.ConnectionError()

    if output_path is None:
        return data
    else:
        with open(output_path, 'wb') as output_file:
            output_file.write(data.content)


def download(url, output_path=None):
    try:
        return download_file(url, output_path)
    except (exceptions.ConnectionError, exceptions.Timeout) as err:
        print(f"[Download exception] {str(err)}")
        print(f"Retrying url '{url}'...")
        return download_file(url, output_path)


def in_date_range(date_str, begin, end):
    if begin and end:
        return begin < datetime.strptime(date_str, '%Y-%m-%d').date() <= end
    elif end:
        return datetime.strptime(date_str, '%Y-%m-%d').date() <= end
    elif begin:
        return begin < datetime.strptime(date_str, '%Y-%m-%d').date()
    return True


def process_mzcr_dataset(begin_date, source_response):
        dataset_json = source_response.json()
        end_date = datetime.strptime(dataset_json['modified'][:10], '%Y-%m-%d').date()
        if end_date == datetime.today().date():
            # Ignore data from this day as it is continuously updated and we would
            # have no way to identify new data when updating our own database because
            # there are no IDs
            end_date = end_date - timedelta(days=1)

        end_date_str = end_date.strftime('%Y-%m-%d')
        if begin_date != end_date:
            return [x for x in dataset_json['data'] if in_date_range(x['datum'], begin_date, end_date)], end_date_str
        else:
            return [], end_date_str


def process_csu_dataset(begin_date, source_response):
        weekly_deaths_csv = source_response.content.decode('utf-8').splitlines(keepends=False)
        selected_columns_indices = [1, 7, 8, 10, 11, 12]
        header = weekly_deaths_csv[0]
        selected_column_names = [header.split(',')[i].strip('\"') for i in selected_columns_indices]
        dataset_csv = weekly_deaths_csv[1:]

        # Transforms a single CSV line into a dict for MongoDB
        def process_line(line):
            columns = line.split(',')
            selected_columns = [columns[i].strip('\"') for i in selected_columns_indices]
            return dict(zip(selected_column_names, selected_columns))

        dataset = [x for x in map(process_line, dataset_csv) if x['vek_txt'] != 'celkem']
        filtered_dataset = [x for x in dataset if in_date_range(x['casref_od'], begin_date, None)]
        return filtered_dataset, dataset[-1]['casref_do']


if __name__ == '__main__':
    db_client = pymongo.MongoClient("mongodb://localhost:27017/")
    print(f"Existing DBs: {db_client.list_database_names()}")
    # db_client.drop_database('covid_data')
    db = db_client['covid_data']
    names = db.list_collection_names()

    data_sources = {
        'confirmed_cases': (URL_COVID_CONFIRMED_CASES, process_mzcr_dataset),
        'daily_deaths': (URL_COVID_DEATHS, process_mzcr_dataset),
        'daily_tests': (URL_COVID_TESTS, process_mzcr_dataset),
        'weekly_deaths': (URL_WEEKLY_DEATHS, process_csu_dataset)
    }

    for collection_name, (source_url, process_function) in data_sources.items():
        begin_date = None
        if collection_name in names:
            collection_metadata = db[collection_name + '.metadata'].find_one()
            begin_date = datetime.strptime(collection_metadata['modified'], '%Y-%m-%d').date()

        collection_data, end_date_str = process_function(begin_date, download(url=source_url))
        if collection_data:
            print(f"Inserting '{len(collection_data)}' documents into '{collection_name}' collection")
            collection = db[collection_name]
            collection.insert_many(collection_data)

        collection_metadata = db[collection_name + '.metadata']
        print(list(collection_metadata.find()))
        collection_metadata.find_one_and_replace({}, {'modified': end_date_str}, upsert=True)

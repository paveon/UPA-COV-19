import pymongo
import requests
import requests.exceptions as exceptions

URL_COVID_CONFIRMED_CASES = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/osoby.json'
URL_COVID_DEATHS = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/umrti.json'
URL_COVID_TESTS = 'https://onemocneni-aktualne.mzcr.cz/api/v2/covid-19/testy.json'

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


if __name__ == '__main__':
    case_overview_report = download(url=URL_COVID_CONFIRMED_CASES).json()
    all_cases = case_overview_report['data']
    print(f"Total confirmed cases: {len(all_cases)}")
    # modification_date = case_overview_report['modified'][:10]

    deaths_report = download(url=URL_COVID_DEATHS).json()
    all_deaths = deaths_report['data']
    print(f"Total deaths: {len(all_deaths)}")

    tests_report = download(url=URL_COVID_TESTS).json()
    daily_tests = tests_report['data']

    db_client = pymongo.MongoClient("mongodb://localhost:27017/")
    print(f"Existing DBs: {db_client.list_database_names()}")

    db = db_client['covid_data']

    case_collection = db['confirmed_cases']
    records = case_collection.insert_many(all_cases)
    # print(f"Insert count: {len(records.inserted_ids)}")

    deaths_collection = db['daily_deaths']
    records = deaths_collection.insert_many(all_deaths)

    tests_collection = db['daily_tests']
    tests_collection.insert_many(daily_tests)

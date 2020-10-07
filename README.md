# UPA-COV-19
[BUT FIT] COVID-19 project for Data Storage and Preparation school course

## Dependencies
- mongodb-server
- Python 3.6 +
  - Django 3.1
  - PyMongo

## Startup
1) Start MongoDB server on localhost:27017 (default) with the following command: `mongod --noauth --dbpath=./MongoDB`
2) Run `python data_collector.py` to import some example data
3) Run `python manage.py migrate` in `./covid` folder for tables migration
3) Start Django debug HTTP server with `python manage.py runserver`
4) Navigate to `http://127.0.0.1:8000/covid_app` in browser

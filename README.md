# algobuilder
AlgoBuilder is a python application for building and running your algo-trading strategies. Algobuilder supports:
* Plugin datasources for collecting price data;
* Plugin feature calculations to build the features that your algo-trading strategies will use; and
* Plugin strategies to calculate trading recommendations from your calculated features.

## Architecture
AlgoBuilder is a distributed application consisting of:
* A web front end to configure your price data source, features and strategies and viewing output;
* A messaging server and task processor for data processing;
* A database to store price data, features and the output from your algo trading strategies.

## Setup
1) Set up your python environment.
2) Set up an empty postgresql database.
3) Set up a RabbitMQ messaging server.   
4) Install the required libraries.

```shell
pip install -r algobuilder/requirements.txt
```

5) Create AlgoBuilders settings file as algobuilder/algobuilder/settings.py. The linked example provides a good initial configuration.

[Initial Configuration Example](README/examples/settings.py)

6) Configure the database connection by editing the DATABASES section in your settings file that you created in step 5.

7) Configure the messaging server connection by editing the CELERY_ parameters in your settings file that you created in step 5.

8) Build the applications' database.

```shell
python manage.py migrate
```

9) Create your admin superuser.
```shell
python manage.py createsuperuser
```

10) Launch the applications web server.
```shell
python manage.py runserver
```

11) Once AlgoBuilder has been set up, you will need to: retrieve price data; calculate features; and calculate trading recommendations. The instructions for these steps are available below:
[Retrieving price data](pricedata/README.md)

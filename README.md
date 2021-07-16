# algobuilder
AlgoBuilder is a python application for building and running your algo-trading strategies. Algobuilder supports:
* Plugin datasources for collecting price data;
* Plugin feature calculations to build the features that your algo-trading strategies will use; and
* Plugin strategies to calculate trading recommendations from your calculated features.

## Setup
1) Set up your python environment.
2) Set up an empty database. This application has been tested on postgresql but should support all main databases.
3) Add any required database drivers to requirements.txt and install. The postgresql drivers have already been installed.   
4) Install the required libraries.

```shell
pip install -r algobuilder/requirements.txt
```

5) Create AlgoBuilders settings file as algobuilder/algobuilder/settings.py. The linked example provides a good initial configuration.

[Initial Configuration Example](README/examples/settings.py)

6) Configure the database connection by editing the DATABASES section in your settings file that you created in step 5.

   
7) Build the applications' database.

```shell
python manage.py migrate
```

8) Create your admin superuser.
```shell
python manage.py createsuperuser
```

9) Launch the applications web server.
```shell
python manage.py runserver
```

10) Once AlgoBuilder has been set up, you will need to: retrieve price data; calculate features; and calculate trading recommendations. The instructions for these steps are available below:
[Retrieving price data](pricedata/README.md)

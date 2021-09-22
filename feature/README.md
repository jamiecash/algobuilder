# Calculating Features
To calculate features from oru price data or other features, you will need to:
* Build your feature; 
* Configure your feature and;
* Configure your feature executions.

## Build your feature
A feature is a calculation that can be performed over the candle data for one or more symbols, or over previously calculated features.

1) Create a python class to implement the feature calculation. This should extend ```feature.feature.FeatureImplementation```.  Your feature implementation  must implement the following method:
   * ```execute(self, feature_execution):``` Calculates the feature and saves the results. The passed feature_execution contains the datasource symbols, candle period and calculation period required to retrieve the candle or feature data for the calculation and the calculation_frequency specifying how often this feature is calculated.
   *  An example that calculates a moving average is available here:

[MovingAverage Example](../plugin_dev/feature_plugins/movingaverage/movingaverage.py)


2) Create a requirements.txt file containing all the modules required for your datasource. 

## Configure your feature
1) Launch the applications web server if it isn't already running.
```shell
python manage.py runserver
```

2) Load the feature as plugin, following the instructions for [loading a plugin](../plugin/README.md).
   
   
3) Navigate to the feature admin page (http://localhost:8000/admin/feature/feature).

4) Click 'ADD FEATURE', then:
   * Provide a name for your feature.
   * Select the FeatureImplementation class that you loaded in step 2.
   * Set the calculation period. This is how much data is used to calculate the feature and can be any pandas timeseries offset: https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases (e.g., A 30-day moving average would use 30 days which would be specified as 30D).
   * Set the calculation frequency. This is how often to run the feature calculation. This should be a string representation of a dict with crontab parameters. e.g. '{"day_of_week": "mon-fri", "hour": 23, "minute": 0}'

5) Add any feature executions here: http://localhost:8000/admin/feature/featureexecution/
   * A feature execution contains one or more datasource_symbols and candle_periods that the feature is being calculated for.

6) When saved, tasks will be added to the 'feature' task queue to calculate your features and will be picked up by your workers.
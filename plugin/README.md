# Plugins
AlgoBuilder supports plugins for:
* DataSources

## Build your plugin
1) Create a python class extending the base class for to your plugin type and implement all required methods. The base classses are as follows:
   * A datasource must extend ```pricedata.datasource.DataSourceImplementation```

2) Create a requirements.txt file containing all the modules required for your plugin. An example has been provided below.

requirements.txt
```text
pandas~=1.3.0
```

## Load your plugin
1) Launch the applications web server if it isn't already running.
```shell
python manage.py runserver
```

2) In a web browser, navigate to the plugin admin page (http://localhost:8000/admin/plugin/plugin/) and log in using the admin account that you created in setup.

3) Click 'ADD PLUGIN', then:
   * Select the python module containing your datasource implementation class that you created in 'Build your datasource'.
   * Select requirements file that you created in 'Build your datasource'.
   * Click save.
   * Run the task processor to prepare your module.
   ```shell
   python manage.py process_tasks
   ```
   
Your plugin should now be installed and ready for use. The admin list page should show the number of classes available in your module. Note that this will only be populated once the task processor has been run.
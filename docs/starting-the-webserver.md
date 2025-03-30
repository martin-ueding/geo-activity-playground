# Starting the Program

Once you have installed the program and [created a base directory](create-a-base-directory.md), you will learn how to start the program in this how-to.

On Linux, execute the following in the command line, where you need to replace `YOUR_BASEDIR` with the path to your base directory.

```bash
geo-activity-playground --basedir YOUR_BASEDIR serve
```

Should that fail with “command not found”, you need to [add local bin to path](add-local-bin-to-path.md).

The webserver will start up and give you a bit of output like this:

```
2023-11-19 17:59:23 geo_activity_playground.importers.strava_api INFO Loading metadata file …
2023-11-19 17:59:23 stravalib.protocol.ApiV3 INFO GET 'https://www.strava.com/api/v3/athlete/activities' with params {'before': None, 'after': 1700392964, 'page': 1, 'per_page': 200}
2023-11-19 17:59:23 geo_activity_playground.importers.strava_api INFO Checking for missing time series data …
 * Serving Flask app 'geo_activity_playground.webui.app'
 * Debug mode: off
2023-11-19 17:59:23 werkzeug INFO WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
2023-11-19 17:59:23 werkzeug INFO Press CTRL+C to quit
```

The warning about the development server is fine. We are using this only to play around, not to power a web service for other users. There might be some more messages about downloading and parsing data. The first startup will take quite some time.

Open <http://127.0.0.1:5000> to open the website in your browser and you will see the user interface.

## Setting host and port

In case you don't like the default value of `127.0.0.1:5000`, you can use the optional command line arguments `--host` and `--port` to specify your values.
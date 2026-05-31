# Acknowledgments

This project builds on many amazing other projects and would not be possible without them.

## Alembic

Database schema changes need to be managed carefully. [Alembic](https://alembic.sqlalchemy.org/) provides a migration framework for SQLAlchemy that autogenerates migration scripts from model changes, keeping the schema in sync across installations.

## Bootstrap CSS

Writing CSS is not a trivial task. For many projects I have been using the [Bootstrap CSS Framework](https://getbootstrap.com/) which provides sensible default values, a 12-column grid system and a lot of components. Using this I didn't have to write any CSS myself and just attach a couple of classes to HTML elements.

## coloredlogs

Log messages in multiple colors are neat. Using the [coloredlogs](https://coloredlogs.readthedocs.io/en/latest/) package we can get these super easily.

## fitdecode

For reading FIT files I use the [fitdecode](https://github.com/polyvertex/fitdecode) library which completely handles all the parsing of this file format.

## Flask

The webserver is implemented with [Flask](https://flask.palletsprojects.com/) which provides a really easy way to get started. Extensions like [Flask-Babel](https://flask-babel.tkte.ch/) add internationalization support and [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) integrates the ORM cleanly into the request lifecycle.

## GeoJSON

Transferring geographic geometry data from the Python code to Leaflet is easiest with using the [GeoJSON format](https://geojson.org/). The [official standard RFC](https://datatracker.ietf.org/doc/html/rfc7946) is a bit hard to read, rather have a look at the [Wikipedia article](https://en.wikipedia.org/wiki/GeoJSON). And there is an [online viewer](https://geojson.io/) that you can try out.

## GitHub

For a smooth open source project one needs a place to share the code and collect issues. [GitHub](https://github.com/) provides all of this for free.

## gpxpy

For reading GPX files I use the [gpxpy](https://github.com/tkrajina/gpxpy) library. This allows me to read those files without having to fiddle with the underlying XML format.

## Gunicorn & Waitress

Running Flask in production requires a proper WSGI server. On Linux [Gunicorn](https://gunicorn.org/) and on Windows [Waitress](https://docs.pylonsproject.org/projects/waitress/) serve this role, handling concurrent requests reliably.

## imageio & imageio-ffmpeg

Generating timelapse videos from activity data requires encoding image sequences into video files. [imageio](https://imageio.readthedocs.io/) together with [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) makes this straightforward from Python.

## Leaflet

The interactive maps on the website are powered by [Leaflet](https://leafletjs.com/), a very easy to use JavaScript library for embedding interactive Open Street Map maps. It can also display GeoJSON geometries natively, of which I also make heavy use.

## Matplotlib

Some visualizations are rendered server-side as static images, for which [Matplotlib](https://matplotlib.org/) is used. The heatmap rendering in particular relies on its image output capabilities.

## NumPy

Numerical array operations underlying much of the data processing are provided by [NumPy](https://numpy.org/), the foundational library for scientific computing in Python.

## Open Street Map

All the maps displayed use tiles from the amazing [Open Street Map](https://www.openstreetmap.org/). This map is created by volunteers, the server hosting is for free. Without these maps this project would be quite boring.

## Pandas

Working with thousands of activities, thousands of tiles and millions of points makes it necessary to have a good library for number crunching structured data. [Pandas](https://pandas.pydata.org/) offers this and gives good performance and many features.

## Parquet

I need to store the intermediate data frames that I generate with Pandas. Storing as JSON has disadvantages because dates are not properly encoded. Also it is a text format and quite verbose. The [Parquet format](https://parquet.apache.org/) is super fast and memory efficient.

## Pillow

Reading and writing raster images — for example photo thumbnails from EXIF data — is handled by [Pillow](https://python-pillow.org/), the friendly PIL fork.

## Python

Almost all of the code here is written in [Python](https://www.python.org/), a very nice and versatile programming language with a vast ecosystem of packages.

## Requests

For doing HTTP requests I use the [Requests](https://requests.readthedocs.io/) library. It provides a really easy to use interface for GET and POST requests.

## Shapely

Geometric operations on GPS tracks and tiles — such as computing intersections or containment — are handled by [Shapely](https://shapely.readthedocs.io/), a library for manipulation and analysis of planar geometric objects.

## SQLAlchemy

All persistent application data is stored via [SQLAlchemy](https://www.sqlalchemy.org/), a comprehensive ORM that abstracts over different SQL databases and makes schema management with Alembic possible.

## Statshunters

The [Statshunters](https://www.statshunters.com/) page allows to import the activities from Strava and do analysis like explorer tiles, Eddington number and many other things. This has served as inspiration for this project.

## Strava

Although I have recorded some of my bike rides, I only really started to record all of them when I started to use [Strava](https://www.strava.com/). This is a nice platform to track all activities. They also offer a social network feature, which I don't really use. They provide some analyses of the data, but they lack some analyses which I have now implemented in this project.

## stravalib

Strava has an API, and with [stravalib](https://stravalib.readthedocs.io/en/latest/) there exists a nice Python wrapper. This makes it much easier to interface with Strava.

## Strava local heatmap

The [Strava local heatmap](https://github.com/remisalmon/Strava-local-heatmap) project provides a script that renders heatmap files from GPX files locally. It has a gorgeous color scheme with a few nifty tricks. The heatmap in this project is inspired by this project that doesn't share the code.

## tcxreader

Support for the TCX file format is provided via [tcxreader](https://github.com/alenrajsp/tcxreader).

## timezonefinder

Activities recorded without an explicit timezone need one assigned based on their coordinates. [timezonefinder](https://timezonefinder.readthedocs.io/) does this lookup efficiently without requiring a network call.

## uv

For managing all the Python package dependencies I use [uv](https://docs.astral.sh/uv/) which makes it very easy to have all the Python project housekeeping with one tool.

## Vega, Altair & VegaFusion

Creating plots that look nice in a browser is hard and I don't like writing JavaScript. Fortunately there is [Vega](https://vega.github.io/vega/) for the beautiful plots and [Altair](https://altair-viz.github.io/index.html) as a Python package that generates the necessary JavaScript for me. [VegaFusion](https://vegafusion.io/) handles server-side pre-aggregation so that large datasets render without shipping all the data to the browser.

## Velo Viewer

I never used [Velo Viewer](https://veloviewer.com/) myself but many people say good things about it. It has so many statistics and inspired many more projects, including this one.

## VitePress

Writing documentation is more fun with a nice tool, therefore I use [VitePress](https://vitepress.dev/) which powers this documentation.

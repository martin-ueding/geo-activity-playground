# Acknowledgments

This project builds on many amazing other projects and would not be possible without them.

## Bootstrap CSS

Writing CSS is not a trivial task. For many projects I have been using the [Bootstrap CSS Framework](https://getbootstrap.com/) which provides sensible default values, a 12-column grid system and a lot of components. Using this I didn't have to write any CSS myself and just attach a couple of classes to HTML elements.

## coloredlogs

Log messages in multiple colors are neat. Using the [coloredlogs](https://coloredlogs.readthedocs.io/en/latest/) package we can get these super easily.

## fitdecode

For reading FIT files I use the [fitdecode](https://github.com/polyvertex/fitdecode) library which completely handles all the parsing of this file format.

## Flask

The webserver is implemented with [Flask](https://flask.palletsprojects.com/) which provides a really easy way to get started. It also ships with a development webserver which is enough for this project at the moment.

## GeoJSON

Transferring geographic geometry data from the Python code to Leaflet is easiest with using the [GeoJSON format](https://geojson.org/). The [official standard RFC](https://datatracker.ietf.org/doc/html/rfc7946) is a bit hard to read, rather have a look at the [Wikipedia article](https://en.wikipedia.org/wiki/GeoJSON). And there is an [online viewer](https://geojson.io/) that you can try out.

## GitHub

For a smooth open source project one needs a place to share the code and collect issues. [GitHub](https://github.com/) provides all of this for free.

## gpxpy

For reading GPX files I use the [gpxpy](https://github.com/tkrajina/gpxpy) library. This allows me to read those files without having to fiddle with the underlying XML format.

## Leaflet

The interactive maps on the website are powered by [Leaflet](https://leafletjs.com/), a very easy to use JavaScript library for embedding interactive Open Street Map maps. It can also display GeoJSON geometries natively, of which I also make heavy use.

## MkDocs

Writing documentation is more fun with a nice tool, therefore I use [MkDocs](https://www.mkdocs.org/) together with [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). This powers this documentation.

## Open Street Map

All the maps displayed use tiles from the amazing [Open Street Map](https://www.openstreetmap.org/). This map is created by volunteers, the server hosting is for free. Without these maps this project would be quite boring.

## Pandas

Working with thousands of activities, thousands of tiles and millions of points makes it necessary to have a good library for number crunching structured data. [Pandas](https://pandas.pydata.org/) offers this and gives good performance and many features.

## Parquet

I need to store the intermediate data frames that I generate with Pandas. Storing as JSON has disadvantages because dates are not properly encoded. Also it is a text format and quite verbose. The [Parquet format](https://parquet.apache.org/) is super fast and memory efficient.

## Poetry

For managing all the Python package dependencies I use [Poetry](https://python-poetry.org/) which makes it very easy to have all the Python project housekeeping with one tool.

## Python

Almost all of the code here is written in [Python](https://www.python.org/), a very nice and versatile programming language with a vast ecosystem of packages.

## Requests

For doing HTTP requests I use the [Requests](https://requests.readthedocs.io/) library. It provides a really easy to use interface for GET and POST requests.

## Scikit-learn

Finding out which cluster is the largest one can either be formed as a graph search problem or as a data science problem. Using the [Scikit-learn](https://scikit-learn.org/stable/) library I can easily use the DBSCAN algorithm to find the clusters of explorer tiles.

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

## Vega & Altair

Creating plots that look nice in a browser is hard and I don't like writing JavaScript. Fortunately there is [Vega](https://vega.github.io/vega/) for the beautiful plots and [Altair](https://altair-viz.github.io/index.html) as a Python package that generates the necessary JavaScript for me.

## Velo Viewer

I never used [Velo Viewer](https://veloviewer.com/) myself but many people say good things about it. It has so many statistics and inspired many more projects, including this one.
# Directory Layout

There are a bunch of files that need to be given to this set of scripts, are used as intermediate files or generated as output. In order to make it clear where everything is, the following document lists all the paths which are relevant to the script.

Everything is relative to a *base directory* which can be passed with the `--basedir` option to the scripts.

# Input

The user has to put data into the following directories in order for it to be picked up.

- `Strava Export`: Contains the exported data from Strava.

- `config.toml`: Configuration file

# Output and cache

The following directories serve as a cache. One can inspect this but doesn't need to work with that directly.

- `Explorer`: Things related to the explorer tiles.

    - `Per Activity`: A data frame with the tiles that have been visited within each activity. Each file is named with the activity ID like `2520340514.parquet`. The columns are `time`, `tile_x`, `tile_y`.
    - `first_time_per_tile.parquet`: A data frame with the first visit datetime for each explorer tile. Columns `time`, `tile_x`, `tile_y`.
    - `missing_tiles.geojson`: A GeoJSON file with square polygons for all missing tiles at the boundary of explored tiles.
    - `missing_tiles.gpx`: The same, just expressed as square tracks in the GPX format.

- `Heatmaps`: Will contain heatmap images generated from the data. They will be called like `Cluster-1.png` with increasing numbers. When one re-generates the heatmaps, the old files will be deleted to make sure that even if the numbers of clusters has been reduced there are no old files remaining.

- `Open Street Map Tiles`: Cached tiles from the Open Street Map. The substructure is `zoom/x/y.png`. Each image has a size of 256×256 pixels.

- `Strava API`: Everything that is downloaded via the Strava API is stored in this subtree.

    - `Data`: The time series data for each activity as a data frame stored in the Parquet format. Filenames are `2589868806.parquet` with the activity IDs. The column names are the following: `time`, `latitude`, `longitude` and optionally `distance`, `altitude`, `heartrate`.
    - `Metadata`: The activity objects from the `stravalib` Python library are stored here as Python pickle objects. The file names are time stamp of the activity start, like `start-1364228189.pickle`.
    - `strava_tokens.json`: Tokens for the Strava API. Contains the *access* and *refresh* tokens.

- `Strava Export Cache`:

    - `Activities`: Same as `Strava API/Data`.
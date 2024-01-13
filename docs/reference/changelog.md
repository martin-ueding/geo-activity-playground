# Changelog

This is the log of high-level changes that I have done in the various versions.

## Version 0

This is the pre-release series. Things haven't settled yet, so each minor version might introduce breaking changes.

- Use locally downloaded tiles for all maps, this way we do not need to download them twice for activities and explorer/heatmap.
- Localize SimRa files to local time zone. [GH-80](https://github.com/martin-ueding/geo-activity-playground/pull/80)
- Parse speed unit from FIT file. There are many devices which record in m/s and not in km/h, yielding too low speeds in the analysis. This is now fixed. [GH-82](https://github.com/martin-ueding/geo-activity-playground/pull/82)

### Version 0.17

- Fix bug which broke the import of `.tcx.gz` files.
- Add `Dockerfile` such that one can easily use this with Docker. [GH-78](https://github.com/martin-ueding/geo-activity-playground/pull/78)
- Add support for the CSV files of the [SimRa Project](https://simra-project.github.io/). [GH-79](https://github.com/martin-ueding/geo-activity-playground/pull/79)

### Version 0.16

#### Version 0.16.4

- Fix syntax error.

#### Version 0.16.3

- Ignore Strava activities without a time series.

#### Version 0.16.2

- Make heatmap images that are downloaded look the same as the interactive one.
- Always emit the path when there is something wrong while parsing an activity file.

#### Version 0.16.1

- Fix handling of TCX files on Windows. On that platform one cannot open the same file twice, therefore my approach failed. Now I close the file properly such that this should work on Windows as well.

#### Version 0.16.0

- Add feature to render heatmap from visible area. [GH-73](https://github.com/martin-ueding/geo-activity-playground/issues/73)
- Remove heatmap image generation from clusters, remove Scikit-Learn dependency.
- Add offsets for equipment. [GH-71](https://github.com/martin-ueding/geo-activity-playground/issues/71)
- Fix number of tile visits in explorer view. [GH-69](https://github.com/martin-ueding/geo-activity-playground/issues/69)
- Add action to convert Strava checkout to our format. [GH-65](https://github.com/martin-ueding/geo-activity-playground/issues/65)
- Filter out some GPS jumps. [GH-54](https://github.com/martin-ueding/geo-activity-playground/issues/54)
- Add simple search function. [GH-70](https://github.com/martin-ueding/geo-activity-playground/issues/70)

### Version 0.15

#### Version 0.15.3

- Create temporary file for TCX parsing in the same directory. There was a problem on Windows where the program didn't have access permissions to the temporary files directory.

#### Version 0.15.2

- Try to open GPX files in binary mode to avoid encoding issues. [GH-74](https://github.com/martin-ueding/geo-activity-playground/issues/74)

#### Version 0.15.1

- Add `if __name__ == "__main__"` clause such that one can use `python -m geo_activity_playground` on Windows.

#### Version 0.15.0

- Export all missing tiles in the viewport, not just the neighbors.
- Automatically retry Strava API when the rate limit is exhausted. [GH-67](https://github.com/martin-ueding/geo-activity-playground/pull/67)
- Give more helpful error messages when the are no activity files present.

### Version 0.14

#### Version 0.14.2

- Fix broken Strava import (bug introduced in 0.14.0).

#### Version 0.14.1

- Fix hard-coded part in KML import (bug introduced in 0.14.0).

#### Version 0.14.0

- Do more calculations eagerly at startup such that the webserver is more responsive. [GH-58](https://github.com/martin-ueding/geo-activity-playground/issues/58)
- Allow setting host and port via the command line. [GH-61](https://github.com/martin-ueding/geo-activity-playground/pull/61)
- Re-add download of explored tiles in area. [GH-63](https://github.com/martin-ueding/geo-activity-playground/issues/63)
- Unify time handling, use UTC for all internal representations. [GH-52](https://github.com/martin-ueding/geo-activity-playground/issues/52)
- Add some sort of KML support that at least works for KML exported by Viking. [GH-62](https://github.com/martin-ueding/geo-activity-playground/issues/62)

### Version 0.13

- Revamp heatmap, use interpolated lines to provide a good experience even at high zoom levels.
  - This also fixes the gaps that were present before. [GH-34](https://github.com/martin-ueding/geo-activity-playground/issues/34)
- Add cache migration functionality.
  - Make sure that cache directory is created beforehand. [GH-55](https://github.com/martin-ueding/geo-activity-playground/issues/55)
- Split tracks into segments based on gaps of 30 seconds in the time data. That helps with interpolation across long distances when one has paused the recording. [GH-47](https://github.com/martin-ueding/geo-activity-playground/issues/47)
  - Fix introduced bug. [GH-56](https://github.com/martin-ueding/geo-activity-playground/issues/56)
- Add cache to heatmap such that it doesn't need to render all activities and only add new activities as needed.
- Add a footer. [GH-49](https://github.com/martin-ueding/geo-activity-playground/issues/49)
- Only export missing tiles in the active viewport. [GH-53](https://github.com/martin-ueding/geo-activity-playground/issues/53)
- Add missing dependency to SciKit Learn again; I was too eager to remove that. [GH-59](https://github.com/martin-ueding/geo-activity-playground/issues/59)

### Version 0.12

- Change coloring of clusters, have a color per cluster. Also mark the square just as an overlay.
- Fix bug with explorer tile page when the maximum cluster or square is just 1. [GH-51](https://github.com/martin-ueding/geo-activity-playground/issues/51)
- Speed up the computation of the latest tiles.

### Version 0.11

- Add last activity in tile to the tooltip. [GH-35](https://github.com/martin-ueding/geo-activity-playground/issues/35)
- Add explorer coloring mode by last activity. [GH-45](https://github.com/martin-ueding/geo-activity-playground/issues/45)
- Actually implement `Activity/{Kind}/{Equipment}/{Name}.{Format}` directory structure.
- Document configuration file.
- Interpolate tracks to find more explorer tiles. [GH-27](https://github.com/martin-ueding/geo-activity-playground/issues/27)
- Fix bug that occurs when activities have no distance information.
- Show time evolution of the number of explorer tiles, the largest cluster and the square size. [GH-33](https://github.com/martin-ueding/geo-activity-playground/issues/33)
- Center map view on biggest explorer cluster.
- Show speed distribution. [GH-42](https://github.com/martin-ueding/geo-activity-playground/issues/42)

### Version 0.10

- Use a grayscale map for the explorer tile maps. [GH-38](https://github.com/martin-ueding/geo-activity-playground/issues/38)
- Explicitly write “0 km” in calendar cells where there are no activities. [GH-39](https://github.com/martin-ueding/geo-activity-playground/issues/39), [GH-40](https://github.com/martin-ueding/geo-activity-playground/pull/40)

### Version 0.9

- Certain exceptions are not skipped when parsing files. This way one can gather all errors at the end. [GH-29](https://github.com/martin-ueding/geo-activity-playground/issues/29)
- Support TCX files. [GH-8](https://github.com/martin-ueding/geo-activity-playground/issues/8)
- Fix equipment view when using the directory source. [GH-25](https://github.com/martin-ueding/geo-activity-playground/issues/25)
- Fix links from the explorer tiles to the first activity that explored them. [GH-30](https://github.com/martin-ueding/geo-activity-playground/issues/30)
- Fix how the API response from Strava is handled during the initial token exchange. [GH-37](https://github.com/martin-ueding/geo-activity-playground/issues/37)

### Version 0.8

#### Version 0.8.3

- Only compute the explorer tile cluster size if there are cluster tiles. Otherwise the DBSCAN algorithm doesn't work anyway. [GH-24](https://github.com/martin-ueding/geo-activity-playground/issues/24)
- Remove allocation of huge array. [GH-23](https://github.com/martin-ueding/geo-activity-playground/issues/23)

#### Version 0.8.2

- Some FIT files apparently have entries with explicit latitude/longitude values, but those are null. I've added a check which skips those points.

#### Version 0.8.1

- Fix reading of FIT files from Wahoo hardware by reading them in binary mode. [GH-20](https://github.com/martin-ueding/geo-activity-playground/issues/20).
- Fix divide-by-zero error in speed calculation. [GH-21](https://github.com/martin-ueding/geo-activity-playground/issues/21)

#### Version 0.8.0

- Make heart rate zone computation a bit more flexibly by offering a lower bound for the resting heart rate.
- Open explorer map centered around median tile.
- Compute explorer cluster and square size, print that. [GH-2](https://github.com/martin-ueding/geo-activity-playground/issues/2)
- Make it compatible with Python versions from 3.9 to 3.11 such that more people can use it. [GH-22](https://github.com/martin-ueding/geo-activity-playground/issues/22)

### Version 0.7

- Add _Squadratinhos_, which are explorer tiles at zoom 17 instead of zoom 14.
- Reduce memory footprint for explorer tile computation.

### Version 0.6

- Interactive map for each activity.
- Color explorer tiles in red, green and blue. [GH-2](https://github.com/martin-ueding/geo-activity-playground/issues/2)
- Directly serve GeoJSON and Vega JSON embedded in the document.
- Automatically detect which source is to be used. [GH-16](https://github.com/martin-ueding/geo-activity-playground/issues/16)
- Fix the name of the script to be `geo-activity-playground` and not just `geo-playground`. [GH-11](https://github.com/martin-ueding/geo-activity-playground/issues/11)
- Add mini maps to the landing page. [GH-9](https://github.com/martin-ueding/geo-activity-playground/issues/9)
- Add fullscreen button to the maps. [GH-4](https://github.com/martin-ueding/geo-activity-playground/issues/4)
- Add favicon. [GH-19](https://github.com/martin-ueding/geo-activity-playground/issues/19)
- Added some more clever caching to the explorer tiles such that loading the page with explorer tiles comes up in just a few seconds.
- Add a triplet of time series plots (distance, altitude, heart rate) for each activity.
- Show plot for heart rate zones per activity. [GH-12](https://github.com/martin-ueding/geo-activity-playground/issues/12)
- Handle activities without any location points. [GH-10](https://github.com/martin-ueding/geo-activity-playground/issues/10)
- Resolve Strava Gear name. [GH-18](https://github.com/martin-ueding/geo-activity-playground/issues/18)
- Add page for equipment. [GH-3](https://github.com/martin-ueding/geo-activity-playground/issues/3)
- Add a pop-up with some metadata about the first visit to the explorer tiles. [GH-14](https://github.com/martin-ueding/geo-activity-playground/issues/14)
- Integrate missing explorer tiles into the web interface. [GH-7](https://github.com/martin-ueding/geo-activity-playground/issues/7).
- Color activity line with speed. [GH-13](https://github.com/martin-ueding/geo-activity-playground/issues/13)
- Add interactive heatmap.
- Add margin to generated heatmaps. [GH-1](https://github.com/martin-ueding/geo-activity-playground/issues/1)

### Version 0.5

- Add some plots for the Eddington number. [GH-3](https://github.com/martin-ueding/geo-activity-playground/issues/3)

### Version 0.4

- Add some more plots.

### Version 0.3

- Start to build web interface with Flask.
- Remove tqdm progress bars and use colorful logging instead.
- Add interactive explorer tile map.

### Version 0.2

- Unity command line entrypoint.
- Crop heatmaps to fit.
- Export missing tiles as GeoJSON.
- Add Strava API.
- Add directory source.

### Version 0.1

#### Version 0.1.3

- Generate some heatmap images.
- Generate an explorer tile video.

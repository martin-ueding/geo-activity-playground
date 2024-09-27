# Changelog

This is the log of high-level changes that I have done in the various versions.

## Version 0

This is the pre-release series. Things haven't settled yet, so each minor version might introduce breaking changes.

### Next

- Use dropdown menus to make navigation a bit smaller.
- [GH-163](https://github.com/martin-ueding/geo-activity-playground/issues/163): Recompute explorer tiles when there are deleted activities. Previously this would lead to `KeyError` when trying to use the heatmap or the explorer tile maps.
- [GH-161](https://github.com/martin-ueding/geo-activity-playground/issues/161): Fix explorer tile clusters and square if one has activities that are not to be considered for achievements.
- [GH-164](https://github.com/martin-ueding/geo-activity-playground/issues/164): Create new function to handle write-and-replace on Windows.
- [GH-155](https://github.com/martin-ueding/geo-activity-playground/issues/155): Use the same scale for all plots with kind, make this configurable in the settings menu.
- Rewrite the documentation start page to make it more appealing and reflect the work in the web interface.

### Version 0.28

- Add settings menu to suppress fields from share pictures.
- Fix spelling mistake in navigation bar.
- Accelerate the tile visit computation.
- Ignore equipment offsets of equipments that don't exist.
- Reset corrupt heatmap cache files.
- [GH-159](https://github.com/martin-ueding/geo-activity-playground/issues/159): Improve password mechanism to protect both upload and settings.
- Document the use of Open Street Map uMap for missing explorer tiles on the go.

### Version 0.27

#### Version 0.27.1

- Fix `num_processes` option.

#### Version 0.27.0

- [GH-128](https://github.com/martin-ueding/geo-activity-playground/issues/128): Let the Strava Checkout importer set the file `strava-last-activity-date.json` which is needed such that the Strava API importer can pick up after all the activities that have been imported via the checkout.
- [GH-143](https://github.com/martin-ueding/geo-activity-playground/issues/143): Use custom CSV parser to read activities that have newlines in their descriptions.
- [GH-146](https://github.com/martin-ueding/geo-activity-playground/issues/146): Make multiprocessing optional with `num_processes = 1` in the configuration.
- [GH-147](https://github.com/martin-ueding/geo-activity-playground/issues/147): Add another safeguard against activities that don't have latitude/longitude data.
- [GH-149](https://github.com/martin-ueding/geo-activity-playground/issues/149): Only pre-compute explorer maps for zoom 14 and 17 by default. Other ones just have to be enabled once. This saves a bit of computing time for most people that don't need to go down to zoom 19.
- [GH-151](https://github.com/martin-ueding/geo-activity-playground/issues/151): Do not fail if version cannot be determined.
- Add settings menu where one can configure various things:
  - Equipment offsets
  - Maximum heart rate for heart rate zones
  - Metadata extractions from paths
  - Privacy zones
  - Strava connection
- The `config.json` replaces the `config.toml` and will automatically be generated.
- Fix bug in explorer tile interpolation that likely doesn't have an effect in practice.

### Version 0.26

#### Version 0.26.3

- [GH-142](https://github.com/martin-ueding/geo-activity-playground/issues/142): Require `pandas >= 2.2.0` to make sure that it knows about `include_groups`.
- [GH-144](https://github.com/martin-ueding/geo-activity-playground/issues/144): Ignore activities without time series when using the Strava Checkout import.

#### Version 0.26.2

- Start with a test suite for the web server that also tests importing.
  - Already fixed a few little bugs with that.
- [GH-141](https://github.com/martin-ueding/geo-activity-playground/issues/141): Fix summary page if there are no activities with steps.

#### Version 0.26.1

- [GH-139](https://github.com/martin-ueding/geo-activity-playground/issues/139), [GH-140](https://github.com/martin-ueding/geo-activity-playground/issues/140): More fixes for Strava archive importer.

#### Version 0.26.0

- Add automatic dark mode.
- Add some more explanation for the Strava connection.
- [GH-138](https://github.com/martin-ueding/geo-activity-playground/issues/138): Fix import from Strava archive that was broken in 0.25.0.
- Style the settings page a bit.

### Version 0.25

- Restructure the way that activities are imported to realize a couple of benefits:
  - Deleting activities is detected now, they are removed from the heatmap.
  - If the code is changed, not everything has to be parsed again. This is especially helpful with regard to the rate-limited Strava API.
  - Some code is deduplicated that had accumulated between activity file parsing and the Strava API.
  - Unfortunately it means that everything needs to parsed again into the new format. I'm sorry about that, especially to you Strava users that need to deal with the rate limiting!
- Add an web interface to connect to Strava API using a shared application such that it becomes much simpler to set up.

- [GH-41](https://github.com/martin-ueding/geo-activity-playground/issues/41): Compute moving time.
- [GH-127](https://github.com/martin-ueding/geo-activity-playground/issues/127): Make calories and steps optional for the share picture.
- [GH-131](https://github.com/martin-ueding/geo-activity-playground/issues/131): Update to the column names in the Strava export.
- [GH-133](https://github.com/martin-ueding/geo-activity-playground/issues/133): Cope with manually recorded activities in Strava export.
- [GH-134](https://github.com/martin-ueding/geo-activity-playground/issues/134): Cope with broken FIT files.

### Version 0.24

#### Version 0.24.2

- [GH-127](https://github.com/martin-ueding/geo-activity-playground/issues/127): Make calories and steps optional for the summary statistics.

#### Version 0.24.1

- [GH-124](https://github.com/martin-ueding/geo-activity-playground/issues/124): Add more timezone handling for Strava API.
- [GH-125](https://github.com/martin-ueding/geo-activity-playground/issues/125): Fix building of Docker container.
- [GH-126](https://github.com/martin-ueding/geo-activity-playground/issues/126): Fix heatmap download.

#### Version 0.24.0

- [GH-43](https://github.com/martin-ueding/geo-activity-playground/issues/43): Added nicer share pictures and privacy zones.
- [GH-95](https://github.com/martin-ueding/geo-activity-playground/issues/05): Display the number of new explorer tiles and squadratinhos per activity.
- [GH-113](https://github.com/martin-ueding/geo-activity-playground/pull/113): Open footer links in a new tab.
- [GH-114](https://github.com/martin-ueding/geo-activity-playground/issues/114): Show total distance and duration in day overview.
- [GH-115](https://github.com/martin-ueding/geo-activity-playground/issues/115): Add more summary statistics and add a "hall of fame" as well.
- [GH-161](https://github.com/martin-ueding/geo-activity-playground/issues/161): Show table for Eddington number, also update the plot to make it a bit easier to read. Add some more explanatory text.
- [GH-118](https://github.com/martin-ueding/geo-activity-playground/issues/118): Fix links in search results.
- [GH-121](https://github.com/martin-ueding/geo-activity-playground/issues/121): Fix link to share picture.
- [GH-122](https://github.com/martin-ueding/geo-activity-playground/issues/122): Convert everything to "timezone naive" dates in order to get rid of inconsistencies.
- [GH-123](https://github.com/martin-ueding/geo-activity-playground/issues/123): Fix startup from empty cache. A cache migration assumed that `activities.parquet` exists. I've added a check.
- Use Flask Blueprints to organize code.
- Remove half-finished "locations" feature from the navigation.
- Allow filtering the heatmap by activity kinds.
- Remove duplicate link to landing page from navigation.

### Version 0.23

- [GH-111](https://github.com/martin-ueding/geo-activity-playground/issues/111): Add password protection for upload.
- Use Flask “flash” messages.
- [GH-110](https://github.com/martin-ueding/geo-activity-playground/issues/110): Support routes that don't have time information attached them. That might be useful if you haven't recorded some particular track but still want it to count towards your heatmap and explorer tiles.

### Version 0.22

- [GH-111](https://github.com/martin-ueding/geo-activity-playground/issues/111): Allow uploading files from within the web UI and parse them directly after uploading.
- Fix bug that lead to re-parsing of activity files during startup.

### Version 0.21

#### Version 0.21.2

- Fix crash in search due to missing `distance/km`.

#### Version 0.21.1

- Add support for Python 3.12.

#### Version 0.21.0

- **Breaking change:** New way to extract metadata from paths and filenames. This uses regular expressions and is more versatile than the heuristic before. If you have used `prefer_metadata_from_file` before, see the [documentation on activity files](../getting-started/using-activity-files.md) for the new way.

- [GH-105](https://github.com/martin-ueding/geo-activity-playground/issues/105): Ignore similar activities that have vanished.
- [GH-106](https://github.com/martin-ueding/geo-activity-playground/issues/106): Be more strict when identifying jumps in activities. Take 30 s and 100 m distance as criterion now.
- [GH-107](https://github.com/martin-ueding/geo-activity-playground/issues/107): Remove warning by fixing a Pandas slice assignment.
- [GH-108](https://github.com/martin-ueding/geo-activity-playground/issues/108): Calories and steps are now extracted from FIT files.
- [GH-109](https://github.com/martin-ueding/geo-activity-playground/issues/109): Better error message when trying to start up without any activity files.

- Removed `imagehash` from the dependencies.
- Single day overview is now linked from each activity.
- Parsing of activity files is now parallelized over all CPU cores and faster than before.
- The coloring of the speed along the activity line doesn't remove outliers any more.

### Version 0.20

- [GH-88](https://github.com/martin-ueding/geo-activity-playground/issues/88): Fix failure to import Strava distance stream due to `unsupported operand type(s) for /: 'list' and 'int'`.
- [GH-90](https://github.com/martin-ueding/geo-activity-playground/issues/90): Take time jumps into account in activity distance computation and the various plots of the activities.
- [GH-91](https://github.com/martin-ueding/geo-activity-playground/pull/91): Import altitude information from GPX files if available.
- [GH-92](https://github.com/martin-ueding/geo-activity-playground/issues/92): Keep identity of activities based on hash of the file content, not the path. This allows to rename activities and just update their metadata, without having duplicates.
- [GH-99](https://github.com/martin-ueding/geo-activity-playground/issues/99): Skip Strava export activities that don't have a file.
- [GH-98](https://github.com/martin-ueding/geo-activity-playground/issues/98): Also accept boolean values in commute column of Strava's `activities.csv`.
- [GH-100](https://github.com/martin-ueding/geo-activity-playground/issues/100): Protect fingerprint computation from bogus values
- [GH-102](https://github.com/martin-ueding/geo-activity-playground/issues/102): Make dependency on `vegafusion[embed]` explicit in the dependencies.
- [GH-103](https://github.com/martin-ueding/geo-activity-playground/issues/103): Delete old pickle file before moving the new one onto it.

### Version 0.19

#### Version 0.19.1

- Fix broken import of CSV files due to missing argument `opener`.

#### Version 0.19.0

- [GH-88](https://github.com/martin-ueding/geo-activity-playground/issues/88): Fix confusion about the internal data type for distance. Most of the time it was in meter, but the display was always in kilometer. In order to make it more clear now, the internal data now only contains the field `distance_km` and everything is represented as kilometer internally now.
- Add more tooltip information in the plot on the landing page.
- [GH-87](https://github.com/martin-ueding/geo-activity-playground/issues/87): Add `prefer_metadata_from_file` configuration option.
- [GH-17](https://github.com/martin-ueding/geo-activity-playground/issues/17): Download calories from Strava via the detailed API.
- Add option `--skip-strava` to the `serve` command in order to start the webserver without reaching out to Strava first. This might be useful if the rate limit has been exceeded.
- [GH-89](https://github.com/martin-ueding/geo-activity-playground/issues/89): Refactor some paths into a module such that there are not so many redundant definitions around.
- [GH-86](https://github.com/martin-ueding/geo-activity-playground/issues/86): Attempt to also read Strava exports that are localized to German, though untested.
- [GH-36](https://github.com/martin-ueding/geo-activity-playground/issues/36): Add a square planner.

### Version 0.18

- Fix _internal server error 500_ when there are not-a-number entries in the speed. [GH-85](https://github.com/martin-ueding/geo-activity-playground/issues/85)
- Display activity source path in detail view.
- Ignore files which start with a period. This should also avoid Apple Quarantine files. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)
- Allow to have both Strava API and activity files.
- Use an existing Strava Export to load activities, retrieve only the remainder from the Strava API.
- In the calender, give the yearly total.

### Version 0.17

#### Version 0.17.5

- Convert FIT sport type enum to strings. [GH-84](https://github.com/martin-ueding/geo-activity-playground/issues/84)

#### Version 0.17.4

- Try to use charset-normalizer to figure out the strange encoding. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

#### Version 0.17.3

- Fix error handler for GPX encoding issues. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

#### Version 0.17.2

- Fix FIT import failure when the sub-sport is none. [GH-84](https://github.com/martin-ueding/geo-activity-playground/issues/84)

#### Version 0.17.1

- Use locally downloaded tiles for all maps, this way we do not need to download them twice for activities and explorer/heatmap.
- Localize SimRa files to local time zone. [GH-80](https://github.com/martin-ueding/geo-activity-playground/pull/80)
- Parse speed unit from FIT file. There are many devices which record in m/s and not in km/h, yielding too low speeds in the analysis. This is now fixed. [GH-82](https://github.com/martin-ueding/geo-activity-playground/pull/82)
- Skip `.DS_Store` files in the activity directory. [GH-81](https://github.com/martin-ueding/geo-activity-playground/pull/81)
- From FIT files we also extract the _grade_, _temperature_ and _GPS accuracy_ fields if they are present. There is no analysis for them yet, though. Also extract the workout name, sport and sub-sport fields from FIT files. [GH-81](https://github.com/martin-ueding/geo-activity-playground/pull/81)
- Add more logging to diagnose Unicode issue on macOS. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

#### Version 0.17.0

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

# Changelog

This is a log of all changes made to the project. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- 
Types of changes

    *Added* for new features.
    *Changed* for changes in existing functionality.
    *Deprecated* for soon-to-be removed features.
    *Removed* for now removed features.
    *Fixed* for any bug fixes.
    *Security* in case of vulnerabilities.

([GH-000](https://github.com/martin-ueding/geo-activity-playground/issues/000))
-->

## Version 0.43.3 — 2025-05-15

Fixed

- Fix adding of new equipment. ([GH-272](https://github.com/martin-ueding/geo-activity-playground/issues/272))
- Fix adding of new activity kind. ([GH-270](https://github.com/martin-ueding/geo-activity-playground/issues/270))
- Gracefully handle case when no activity kinds are considered for achievements but no prior tiles have been extracted. ([GH-274](https://github.com/martin-ueding/geo-activity-playground/issues/274))

## Version 0.43.2 — 2025-05-06

Fixed:

- Allow POST request to `/settings/admin-password`. ([GH-269](https://github.com/martin-ueding/geo-activity-playground/issues/269))

## Version 0.43.1 — 2025-05-06

Fixed:

- Handle NaT (not a time) values gracefully. ([GH-268](https://github.com/martin-ueding/geo-activity-playground/issues/268))
- Make entry page robust against routes without a start.
- Make search page robust against routes without time information.
- Make activity page robust against missing tiles. ([GH-261](https://github.com/martin-ueding/geo-activity-playground/issues/261))
- Make activity page robust against routes. ([GH-266](https://github.com/martin-ueding/geo-activity-playground/issues/266))
- Enforce that at least one activity kind is considered for achievements. ([GH-261](https://github.com/martin-ueding/geo-activity-playground/issues/261))

## Version 0.43.0 — 2025-04-27

Added:

- Add photo upload that matches photos automatically to activities. Photos are shown on the activity page and also on the map for each activity. There is a global map with all photos. ([GH-247](https://github.com/martin-ueding/geo-activity-playground/issues/247))
- Add tag filter to search form. ([GH-242](https://github.com/martin-ueding/geo-activity-playground/issues/242))
- Mention CubeTrek on page with similar projects.

Changed:

- The search queries work directly against the database.
- Remove some redundant metadata from the activity overview.

Fixed:

- Filter not-a-time dates when importing into the database. ([GH-266](https://github.com/martin-ueding/geo-activity-playground/issues/266))

Removed:

- Search history is broken for now.

## Version 0.42.0 — 2025-04-26

Added:

- Add page to documentation about similar projects.
- Add more detailed error message when activity import failed. ([GH-266](https://github.com/martin-ueding/geo-activity-playground/issues/266))
- Allow setting tags for activities. There is a separate tag manager in the settings panel. Search is still missing. ([GH-242](https://github.com/martin-ueding/geo-activity-playground/issues/242))
- Add search filter for activity distance. ([GH-267](https://github.com/martin-ueding/geo-activity-playground/issues/267))

Fixed:

- Iterate over activities in temporal order. This could have lead to screwed up explorer tile history. Delete `Cache/tile-state-2.pickle` and `Cache/work-tracker-tile-state.pickle` to regenerate that part as needed.
- Try to be more robust with NaN values when importing activities. ([GH-266](https://github.com/martin-ueding/geo-activity-playground/issues/266))
- Fix database directory when using a relative basedir. ([GH-256](https://github.com/martin-ueding/geo-activity-playground/issues/256))

Removed:

- Remove dict based access to `Activity` class.

## Version 0.41.0 — 2025-04-20

Added:

- Add "elevation Eddington number" page, which shows an Eddington number but with elevation instead of distance. ([GH-254](https://github.com/martin-ueding/geo-activity-playground/issues/254))
- In the activity view, there is a map with a colored track line. The coloring was based only on speed, now it can also show elevation. ([GH-254](https://github.com/martin-ueding/geo-activity-playground/issues/254))
- On the landing page there is a plot with the elevation gain in the past weeks. ([GH-254](https://github.com/martin-ueding/geo-activity-playground/issues/254))
- Add a fast server-side rendering mode for explorer tiles. This is much faster with arbitrary many explored tiles, it just doesn't show nice metadata yet. This can also be used as a tile source for external planning tools. ([GH-243](https://github.com/martin-ueding/geo-activity-playground/issues/243))
- Add data model for tags, though no user interface yet.

Changed:

- Use database to populate entry page.
- Make explorer tile page load much faster.

Fixed:

- Fix startup without activities. ([GH-263](https://github.com/martin-ueding/geo-activity-playground/issues/263))

## Version 0.40.1 — 2025-04-18

Fixed:

- Fix moving time for activities with zero elapsed time or moving time. ([GH-260](https://github.com/martin-ueding/geo-activity-playground/issues/260))
- Handle `/` in activity name when converting from Strava. ([GH-259](https://github.com/martin-ueding/geo-activity-playground/issues/259))

Removed:

- Remove “commute” concept from Strava converter. ([GH-259](https://github.com/martin-ueding/geo-activity-playground/issues/259))

## Version 0.40.0 — 2025-04-18

Added:

- Add a plot builder. ([GH-258](https://github.com/martin-ueding/geo-activity-playground/issues/258))

Changed:

- Rename “altitude” to “elevation”. _Altitude_ describes the height between ground and something in the sky, _elevation_ describes the hight of a point of earth with respect to sea level. Hence for our outdoor activities, “elevation” is more fitting. ([GH-253](https://github.com/martin-ueding/geo-activity-playground/issues/253))

Fixed:

- Use `pathlib` to construct database path correctly on Windows. ([GH-256](https://github.com/martin-ueding/geo-activity-playground/issues/256))
- Try to support German localization in Strava conversion. ([GH-259](https://github.com/martin-ueding/geo-activity-playground/issues/259))
- Fix moving time for activities without duration. ([GH-260](https://github.com/martin-ueding/geo-activity-playground/issues/260))

## Version 0.39.1 — 2025-04-17

Fixed:

- Fix import of activities into database. ([GH-257](https://github.com/martin-ueding/geo-activity-playground/issues/257))


## Version 0.39.0 — 2025-04-15

Added:

- Add trim feature for activities, although the user interface is quite basic at the moment. ([GH-234](https://github.com/martin-ueding/geo-activity-playground/issues/234))
- Add a plot for monthly equipment usage. ([GH-251](https://github.com/martin-ueding/geo-activity-playground/issues/251))
- Add bubble chart with activities. ([GH-252](https://github.com/martin-ueding/geo-activity-playground/issues/252))
- Add installation instructions for macOS. ([GH-235](https://github.com/martin-ueding/geo-activity-playground/issues/235))
- Add link to changelog from the version string. ([GH-244](https://github.com/martin-ueding/geo-activity-playground/issues/244))
- Add documentation for noisy elevation gain.
- README file now contains much more content. ([GH-250](https://github.com/martin-ueding/geo-activity-playground/issues/250))
- Add bookmark function for the square planner. ([GH-210](https://github.com/martin-ueding/geo-activity-playground/issues/210))

Changed:

- ⚠️ The program now stores actual state in the directory and not merely caches the parsed data. This means that one can make changes to the data within the web interface and that will be stored in the database and not in the original files. This is a change in scope of the program so far, which has been only a mere viewer. Data is now stored in a database (SQLite) instead of a Parquet file. Deleting the `Cache` directory will not result in data loss, but deleting `database.sqlite` will.
- Make all tables responsive. ([GH-233](https://github.com/martin-ueding/geo-activity-playground/issues/233))
- Suggest to upgrade with `--pip-args "--upgrade-strategy eager"` to get the latest versions of dependencies as well.
- Display activities from the past 30 days on the landing page, grouped by day.
- Only show relevant data on the activity page.
- The split between controllers and blueprints is removed, making the code less complex at the cost of not separating code from the web framework. ([GH-214](https://github.com/martin-ueding/geo-activity-playground/issues/214))
- Settings pages for equipment offsets and activity kinds to consider for achievements have been converted into management pages for equipments and activity kinds.

Removed:

- Deleting an activity file from the `Activities` directory will not remove them from the database any more.
- Remove “commute” property as it is unclear what that even means and what to do with that.
- Remove current activity kind renaming functionality. Will be replaced by something acting on the database later.

Fixed:

- Make arrows in square planner look consistent on Windows. ([GH-237](https://github.com/martin-ueding/geo-activity-playground/issues/237))

## Version 0.38.2 — 2025-03-29

Added:

- Add tooltips to all charts and add a sensible amount of decimal places. ([GH-231](https://github.com/martin-ueding/geo-activity-playground/issues/231))

Changed:

- ⚠️ `master` is renamed to `main`.
- Format changelog according to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- Restructure the documentation such that it hopefully is more inviting for new users.
- Share picture now scales with viewport. ([GH-232](https://github.com/martin-ueding/geo-activity-playground/issues/232))
- Activity details and map go below each other on small viewports. ([GH-232](https://github.com/martin-ueding/geo-activity-playground/issues/232))

Removed:

- Remove documentation of individual features as it is hard to maintain and doesn't seem to bring much value. With the web interface it is better to invest into usability or inline explanation instead.

## Version 0.38.1 — 2025-03-16

Fixed:

- Do not fail if elevation gain is missing. ([GH-227](https://github.com/martin-ueding/geo-activity-playground/issues/227))
- Update pyarrow dependency from 18 to 19 to help with dependency issues.

## Version 0.38.0 — 2025-01-26

Added:

- Show history of recent filters.
- Allow saving filters as favorites.
- Add average speed to various views. ([GH-192](https://github.com/martin-ueding/geo-activity-playground/issues/192))
- Add elevation gain extraction. Be aware that this is very noisy for most GPS devices as they lack a barometer. ([GH-199](https://github.com/martin-ueding/geo-activity-playground/issues/199))
- "Hall of Fame" includes additional nominations per equipment used.
- Add Eddington number with activities from just single years. ([GH-195](https://github.com/martin-ueding/geo-activity-playground/issues/195))
- Add time evolution of Eddington number. ([GH-195](https://github.com/martin-ueding/geo-activity-playground/issues/195))
- Add Eddington number but grouped by weeks instead of days. ([GH-195](https://github.com/martin-ueding/geo-activity-playground/issues/195))

Fixed:

- Sort activities by date descending in the search view. ([GH-225](https://github.com/martin-ueding/geo-activity-playground/issues/225))
- Replace empty strings in kind and equipment with literal "Unknown". ([GH-224](https://github.com/martin-ueding/geo-activity-playground/issues/224))
- Remove duplicate legend for day overview. ([GH-223](https://github.com/martin-ueding/geo-activity-playground/issues/223))
- Add authentication to enablement of additional zoom levels. ([GH-222](https://github.com/martin-ueding/geo-activity-playground/issues/222))
- Sort equipment details by last use.
- Make Eddington plots only zoomable in one axis.
- Add uniform kind scale to equipment usage plots.

## Version 0.37.0 — 2025-01-18

Added:

- Add unified activity filter for activity overview, heatmap, Eddington number, summary statistics. ([GH-215](https://github.com/martin-ueding/geo-activity-playground/issues/215))

Fixed:

- Fix Docker build with Poetry 2.0. ([GH-218](https://github.com/martin-ueding/geo-activity-playground/issues/218))
- Fix equipment summary when routes are present. ([GH-219](https://github.com/martin-ueding/geo-activity-playground/issues/219))

## Version 0.36.2 — 2025-01-10

Fixed:

- Try to fix search view for routes without time information. ([GH-217](https://github.com/martin-ueding/geo-activity-playground/issues/217))

## Version 0.36.1 — 2025-01-06

Fixed:

- Remove integrity from assets. ([GH-216](https://github.com/martin-ueding/geo-activity-playground/issues/216))

## Version 0.36.0 — 2025-01-04

Added:

- Add date filter to heatmap. ([GH-212](https://github.com/martin-ueding/geo-activity-playground/issues/212))
- Add square planner to navigation. ([GH-209](https://github.com/martin-ueding/geo-activity-playground/issues/209))

Changed:

- Clip speed coloring with IQR to remove outliers. ([GH-211](https://github.com/martin-ueding/geo-activity-playground/issues/211))
- Remove multiprocessing for parsing activities due to warnings about multithreading. This unfortunately slows down initial processing. ([GH-206](https://github.com/martin-ueding/geo-activity-playground/issues/206))
- Start to simplify the controller structure. ([GH-214](https://github.com/martin-ueding/geo-activity-playground/issues/214))
- Encode kinds via integers in heatmap to protect it against weird kind names containing control symbols. ([GH-213](https://github.com/martin-ueding/geo-activity-playground/issues/213))

## Version 0.35.1 — 2025-01-03

Changed:

- Do some internal changes to the map background generation for share pictures.
- Do some refactoring in the web code.

Fixed:

- Support activity files with uppercase suffix. ([GH-208](https://github.com/martin-ueding/geo-activity-playground/issues/208))

## Version 0.35.0 — 2025-01-01

Added:

- Add button to explorer tile map to remove map background.

## Version 0.34.2 — 2024-12-31

Changed:

- Host another JavaScript asset locally.

## Version 0.34.1 — 2024-12-30

Changed:

- Host all assets locally to avoid using CDNs.

## Version 0.34.0 — 2024-12-21

Added:

- Add a share picture per day. ([GH-157](https://github.com/martin-ueding/geo-activity-playground/issues/157))

Fixed:

- Enforce UTF-8 encoding when reading the `activities.csv` from the Strava export. ([GH-197](https://github.com/martin-ueding/geo-activity-playground/issues/197))
- Make CSV header parsing a bit more robust. ([GH-197](https://github.com/martin-ueding/geo-activity-playground/issues/197))
- Correct label for equipment "kinds" plot. ([GH-201](https://github.com/martin-ueding/geo-activity-playground/issues/201))
- Fix documentation, remove `--skip-strava` and replace it with `--skip-reload`. ([GH-203](https://github.com/martin-ueding/geo-activity-playground/issues/203))
- Fix mismatch between ISO week and regular year. ([GH-205](https://github.com/martin-ueding/geo-activity-playground/issues/205))

## Version 0.33.4 — 2024-12-07

Added:

- Add compatibility for Python 3.13.

## Version 0.33.3 — 2024-11-24

Fixed:

- Fix startup without any activities. ([GH-200](https://github.com/martin-ueding/geo-activity-playground/issues/200))
- Fix upload when there is no `Activities` directory.

## Version 0.33.2 — 2024-11-17

Fixed:

- Fix explorer map. The problem was that VS Code auto-formatted the embedded JavaScript and created syntax errors. ([GH-198](https://github.com/martin-ueding/geo-activity-playground/issues/198))

## Version 0.33.1 — 2024-11-16

Fixed:

- Fix little bug with `_meta`. ([GH-156](https://github.com/martin-ueding/geo-activity-playground/issues/156))

## Version 0.33.0 — 2024-11-14

Added:

- Make heatmap colormap configurable via web UI.
- Make tile map URL configurable via configuration file. ([GH-196](https://github.com/martin-ueding/geo-activity-playground/issues/196))

Changed:

- Make daily pulse plot per year in tabs.

## Version 0.32.0 — 2024-11-12

Added:

- Add config option `ignore_suffixes` which can be set to something like `[".kml"]` to ignore certain file types. ([GH-173](https://github.com/martin-ueding/geo-activity-playground/issues/173))

Changed:

- Include all activities in the summary, even those which are not to be considered for achievements.
- Make share picture always the same size independent of the content.

Removed:

- Remove debug print.

## Version 0.31.0 — 2024-11-01

Added:

- Add metadata editing functionality with override files. ([GH-156](https://github.com/martin-ueding/geo-activity-playground/issues/156))

Changed:

- Make date and time formats better to read.

Fixed:

- Fix heatmap tile cache expiry in cases where the activity kind has changed. ([GH-189](https://github.com/martin-ueding/geo-activity-playground/issues/189))

## Version 0.30.0 — 2024-10-25

Added:

- Add new search functionality that also serves as an overview over all activities. ([GH-174](https://github.com/martin-ueding/geo-activity-playground/issues/174))
- Make track segmentation configurable with a configuration setting. ([GH-162](https://github.com/martin-ueding/geo-activity-playground/issues/162))
- Remove `root=` prefix in activity kind when importing from Strava. ([GH-188](https://github.com/martin-ueding/geo-activity-playground/issues/188))
- Visualize cadence on the activity page.
- Add option to rename activity kinds. ([GH-188](https://github.com/martin-ueding/geo-activity-playground/issues/188))

Changed:

- Update favicon to new logo. ([GH-187](https://github.com/martin-ueding/geo-activity-playground/issues/187))
- Clicking on table headers will sort the tables now. ([GH-168](https://github.com/martin-ueding/geo-activity-playground/issues/168))

## Version 0.29.2 — 2024-10-14

Added:

- Mention Organic Maps. ([GH-175](https://github.com/martin-ueding/geo-activity-playground/issues/175))

Changed:

- Documentation improvements by [beautiful-orca](https://github.com/beautiful-orca): [GH-180](https://github.com/martin-ueding/geo-activity-playground/pull/180), [GH-181](https://github.com/martin-ueding/geo-activity-playground/pull/181), [GH-182](https://github.com/martin-ueding/geo-activity-playground/pull/182), [GH-183](https://github.com/martin-ueding/geo-activity-playground/pull/183), [GH-185](https://github.com/martin-ueding/geo-activity-playground/pull/185)
- Use Python 3.12 in Docker. ([GH-184](https://github.com/martin-ueding/geo-activity-playground/issues/184))

Fixed:

- Fix display of number of new tiles in activity view. ([GH-178](https://github.com/martin-ueding/geo-activity-playground/issues/178))
- Fix distance from new `stravalib` version. ([GH-177](https://github.com/martin-ueding/geo-activity-playground/issues/177))
- Work around Pandas deprecation message. ([GH-179](https://github.com/martin-ueding/geo-activity-playground/issues/179))
- Do not modify filename on upload any more. ([GH-176](https://github.com/martin-ueding/geo-activity-playground/issues/176))

## Version 0.29.1 — 2024-10-03

Fixed:

- Fix explorer tile export. ([GH-167](https://github.com/martin-ueding/geo-activity-playground/issues/167))
- Fix import of KML files with waypoints. ([GH-169](https://github.com/martin-ueding/geo-activity-playground/issues/169))

## Version 0.29.0 — 2024-09-30

Added:

- Add map with new explorer tiles to activity view. ([GH-166](https://github.com/martin-ueding/geo-activity-playground/issues/166))

Changed:

- Use dropdown menus to make navigation a bit smaller.
- Use the same scale for all plots with kind, make this configurable in the settings menu. ([GH-155](https://github.com/martin-ueding/geo-activity-playground/issues/155))
- Rewrite the documentation start page to make it more appealing and reflect the work in the web interface.

Fixed:

- Recompute explorer tiles when there are deleted activities. Previously this would lead to `KeyError` when trying to use the heatmap or the explorer tile maps. ([GH-163](https://github.com/martin-ueding/geo-activity-playground/issues/163))
- Fix explorer tile clusters and square if one has activities that are not to be considered for achievements. ([GH-161](https://github.com/martin-ueding/geo-activity-playground/issues/161))
- Create new function to handle write-and-replace on Windows. ([GH-164](https://github.com/martin-ueding/geo-activity-playground/issues/164))
- Update version of `stravalib` and with that also `pydantic`. That fixes a bug with `recursive_guard`. ([GH-160](https://github.com/martin-ueding/geo-activity-playground/issues/160))

## Version 0.28.0 — 2024-09-07

Added:

- Add settings menu to suppress fields from share pictures.
- Document the use of Open Street Map uMap for missing explorer tiles on the go.

Changed:

- Accelerate the tile visit computation.

Fixed:

- Fix spelling mistake in navigation bar.
- Ignore equipment offsets of equipments that don't exist.
- Reset corrupt heatmap cache files.

Security:

- Improve password mechanism to protect both upload and settings. ([GH-159](https://github.com/martin-ueding/geo-activity-playground/issues/159))

## Version 0.27.1 — 2024-08-14

Fixed:

- Fix `num_processes` option.

## Version 0.27.0 — 2024-08-11

Added:

- Add another safeguard against activities that don't have latitude/longitude data. ([GH-147](https://github.com/martin-ueding/geo-activity-playground/issues/147))
- Make multiprocessing optional with `num_processes = 1` in the configuration. ([GH-146](https://github.com/martin-ueding/geo-activity-playground/issues/146))
- Add settings menu where one can configure various things:
  - Equipment offsets
  - Maximum heart rate for heart rate zones
  - Metadata extractions from paths
  - Privacy zones
  - Strava connection

Changed:

- Let the Strava Checkout importer set the file `strava-last-activity-date.json` which is needed such that the Strava API importer can pick up after all the activities that have been imported via the checkout. ([GH-128](https://github.com/martin-ueding/geo-activity-playground/issues/128))
- Use custom CSV parser to read activities that have newlines in their descriptions. ([GH-143](https://github.com/martin-ueding/geo-activity-playground/issues/143))
- Only pre-compute explorer maps for zoom 14 and 17 by default. Other ones just have to be enabled once. This saves a bit of computing time for most people that don't need to go down to zoom 19. ([GH-149](https://github.com/martin-ueding/geo-activity-playground/issues/149))
- The `config.json` replaces the `config.toml` and will automatically be generated.

Fixed:

- Do not fail if version cannot be determined. ([GH-151](https://github.com/martin-ueding/geo-activity-playground/issues/151))
- Fix bug in explorer tile interpolation that likely doesn't have an effect in practice.

## Version 0.26.3 — 2024-08-08

Fixed:

- Require `pandas >= 2.2.0` to make sure that it knows about `include_groups`. ([GH-142](https://github.com/martin-ueding/geo-activity-playground/issues/142))
- Ignore activities without time series when using the Strava Checkout import. ([GH-144](https://github.com/martin-ueding/geo-activity-playground/issues/144))

## Version 0.26.2 — 2024-08-06

Added:

- Start with a test suite for the web server that also tests importing.
  - Already fixed a few little bugs with that.

Fixed:

- Fix summary page if there are no activities with steps. ([GH-141](https://github.com/martin-ueding/geo-activity-playground/issues/141))

## Version 0.26.1 — 2024-08-06

Fixed:

- More fixes for Strava archive importer. ([GH-139](https://github.com/martin-ueding/geo-activity-playground/issues/139), [GH-140](https://github.com/martin-ueding/geo-activity-playground/issues/140))

## Version 0.26.0 — 2024-08-06

Added:

- Add automatic dark mode.
- Add some more explanation for the Strava connection.

Changed:

- Style the settings page a bit.

Fixed:

- Fix import from Strava archive that was broken in 0.25.0. ([GH-138](https://github.com/martin-ueding/geo-activity-playground/issues/138))

## Version 0.25.0 — 2024-08-05

Added:

- Add an web interface to connect to Strava API using a shared application such that it becomes much simpler to set up.
- Compute moving time. ([GH-41](https://github.com/martin-ueding/geo-activity-playground/issues/41))
- Make calories and steps optional for the share picture. ([GH-127](https://github.com/martin-ueding/geo-activity-playground/issues/127))

Changed:

- Restructure the way that activities are imported to realize a couple of benefits:
  - Deleting activities is detected now, they are removed from the heatmap.
  - If the code is changed, not everything has to be parsed again. This is especially helpful with regard to the rate-limited Strava API.
  - Some code is deduplicated that had accumulated between activity file parsing and the Strava API.
  - Unfortunately it means that everything needs to parsed again into the new format. I'm sorry about that, especially to you Strava users that need to deal with the rate limiting!
- Update to the column names in the Strava export. ([GH-131](https://github.com/martin-ueding/geo-activity-playground/issues/131))

Fixed:

- Cope with manually recorded activities in Strava export. ([GH-133](https://github.com/martin-ueding/geo-activity-playground/issues/133))
- Cope with broken FIT files. ([GH-134](https://github.com/martin-ueding/geo-activity-playground/issues/134))

## Version 0.24.2 — 2024-07-29

Fixed:

- Make calories and steps optional for the summary statistics. ([GH-127](https://github.com/martin-ueding/geo-activity-playground/issues/127))

## Version 0.24.1 — 2024-07-27

Fixed:

- Add more timezone handling for Strava API. ([GH-124](https://github.com/martin-ueding/geo-activity-playground/issues/124))
- Fix building of Docker container. ([GH-125](https://github.com/martin-ueding/geo-activity-playground/issues/125))
- Fix heatmap download. ([GH-126](https://github.com/martin-ueding/geo-activity-playground/issues/126))

## Version 0.24.0 — 2024-07-26

Added:

- Added nicer share pictures and privacy zones. ([GH-43](https://github.com/martin-ueding/geo-activity-playground/issues/43))
- Display the number of new explorer tiles and squadratinhos per activity. ([GH-95](https://github.com/martin-ueding/geo-activity-playground/issues/05))
- Show total distance and duration in day overview. ([GH-114](https://github.com/martin-ueding/geo-activity-playground/issues/114))
- Add more summary statistics and add a "hall of fame" as well. ([GH-115](https://github.com/martin-ueding/geo-activity-playground/issues/115))
- Show table for Eddington number, also update the plot to make it a bit easier to read. Add some more explanatory text. ([GH-161](https://github.com/martin-ueding/geo-activity-playground/issues/161))
- Allow filtering the heatmap by activity kinds.

Changed:

- Open footer links in a new tab. ([GH-113](https://github.com/martin-ueding/geo-activity-playground/pull/113))
- Fix links in search results. ([GH-118](https://github.com/martin-ueding/geo-activity-playground/issues/118))
- Fix link to share picture. ([GH-121](https://github.com/martin-ueding/geo-activity-playground/issues/121))
- Convert everything to "timezone naive" dates in order to get rid of inconsistencies. ([GH-122](https://github.com/martin-ueding/geo-activity-playground/issues/122))
- Use Flask Blueprints to organize code.

Removed:

- Remove half-finished "locations" feature from the navigation.
- Remove duplicate link to landing page from navigation.

Fixed:

- Fix startup from empty cache. A cache migration assumed that `activities.parquet` exists. I've added a check. ([GH-123](https://github.com/martin-ueding/geo-activity-playground/issues/123))

## Version 0.23.0 — 2024-06-22

Added:

- Use Flask “flash” messages.
- Support routes that don't have time information attached them. That might be useful if you haven't recorded some particular track but still want it to count towards your heatmap and explorer tiles. ([GH-110](https://github.com/martin-ueding/geo-activity-playground/issues/110))

Security:

- Add password protection for upload. ([GH-111](https://github.com/martin-ueding/geo-activity-playground/issues/111))

## Version 0.22.0 — 2024-06-16

Added:

- Allow uploading files from within the web UI and parse them directly after uploading. ([GH-111](https://github.com/martin-ueding/geo-activity-playground/issues/111))

Fixed:

- Fix bug that lead to re-parsing of activity files during startup.

## Version 0.21.2 — 2024-06-09

Fixed:

- Fix crash in search due to missing `distance/km`.

## Version 0.21.1 — 2024-06-09

Added:

- Add support for Python 3.12.

## Version 0.21.0 — 2024-06-09

Added:

- Calories and steps are now extracted from FIT files. ([GH-108](https://github.com/martin-ueding/geo-activity-playground/issues/108))
- Parsing of activity files is now parallelized over all CPU cores and faster than before.

Changed:

- ⚠️ New way to extract metadata from paths and filenames. This uses regular expressions and is more versatile than the heuristic before. If you have used `prefer_metadata_from_file` before, see the documentation on activity files for the new way.
- Ignore similar activities that have vanished. ([GH-105](https://github.com/martin-ueding/geo-activity-playground/issues/105))
- Be more strict when identifying jumps in activities. Take 30 s and 100 m distance as criterion now. ([GH-106](https://github.com/martin-ueding/geo-activity-playground/issues/106))
- Better error message when trying to start up without any activity files. ([GH-109](https://github.com/martin-ueding/geo-activity-playground/issues/109))
- Single day overview is now linked from each activity.
- The coloring of the speed along the activity line doesn't remove outliers any more.

Fixed:

- Remove warning by fixing a Pandas slice assignment. ([GH-107](https://github.com/martin-ueding/geo-activity-playground/issues/107))

Removed:

- Removed `imagehash` from the dependencies.

## Version 0.20.0 — 2024-03-02

Added:

- Import altitude information from GPX files if available. ([GH-91](https://github.com/martin-ueding/geo-activity-playground/pull/91))
- Also accept boolean values in commute column of Strava's `activities.csv`. ([GH-98](https://github.com/martin-ueding/geo-activity-playground/issues/98))

Changed:

- Take time jumps into account in activity distance computation and the various plots of the activities. ([GH-90](https://github.com/martin-ueding/geo-activity-playground/issues/90))
- Keep identity of activities based on hash of the file content, not the path. This allows to rename activities and just update their metadata, without having duplicates. ([GH-92](https://github.com/martin-ueding/geo-activity-playground/issues/92))
- Skip Strava export activities that don't have a file. ([GH-99](https://github.com/martin-ueding/geo-activity-playground/issues/99))
- Protect fingerprint computation from bogus values ([GH-100](https://github.com/martin-ueding/geo-activity-playground/issues/100))
- Make dependency on `vegafusion[embed]` explicit in the dependencies. ([GH-102](https://github.com/martin-ueding/geo-activity-playground/issues/102))

Fixed:

- Fix failure to import Strava distance stream due to `unsupported operand type(s) for /: 'list' and 'int'`. ([GH-88](https://github.com/martin-ueding/geo-activity-playground/issues/88))
- Delete old pickle file before moving the new one onto it to get it working on Windows. ([GH-103](https://github.com/martin-ueding/geo-activity-playground/issues/103))

## Version 0.19.1 — 2024-02-03

Fixed:

- Fix broken import of CSV files due to missing argument `opener`.

## Version 0.19.0 — 2024-02-03

Added:

- Add more tooltip information in the plot on the landing page.
- Add `prefer_metadata_from_file` configuration option. ([GH-87](https://github.com/martin-ueding/geo-activity-playground/issues/87))
- Download calories from Strava via the detailed API. ([GH-17](https://github.com/martin-ueding/geo-activity-playground/issues/17))
- Add option `--skip-strava` to the `serve` command in order to start the webserver without reaching out to Strava first. This might be useful if the rate limit has been exceeded.
- Attempt to also read Strava exports that are localized to German, though untested. ([GH-86](https://github.com/martin-ueding/geo-activity-playground/issues/86))
- Add a square planner. ([GH-36](https://github.com/martin-ueding/geo-activity-playground/issues/36))

Changed:

- Refactor some paths into a module such that there are not so many redundant definitions around. ([GH-89](https://github.com/martin-ueding/geo-activity-playground/issues/89))

Fixed:

- Fix confusion about the internal data type for distance. Most of the time it was in meter, but the display was always in kilometer. In order to make it more clear now, the internal data now only contains the field `distance_km` and everything is represented as kilometer internally now. ([GH-88](https://github.com/martin-ueding/geo-activity-playground/issues/88))

## Version 0.18.0 — 2024-01-26

Added:

- Display activity source path in detail view.
- Allow to have both Strava API and activity files.
- In the calender, give the yearly total.

Changed:

- Use an existing Strava Export to load activities, retrieve only the remainder from the Strava API.
- Ignore files which start with a period. This should also avoid Apple Quarantine files. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

Fixed:

- Fix _internal server error 500_ when there are not-a-number entries in the speed. [GH-85](https://github.com/martin-ueding/geo-activity-playground/issues/85)

## Version 0.17.5 — 2024-01-14

Fixed:

- Convert FIT sport type enum to strings. [GH-84](https://github.com/martin-ueding/geo-activity-playground/issues/84)

## Version 0.17.4 — 2024-01-14

Changed:

- Try to use charset-normalizer to figure out the strange encoding. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

## Version 0.17.3 — 2024-01-14

Fixed:

- Fix error handler for GPX encoding issues. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

## Version 0.17.2 — 2024-01-14

Fixed:

- Fix FIT import failure when the sub-sport is none. [GH-84](https://github.com/martin-ueding/geo-activity-playground/issues/84)

## Version 0.17.1 — 2024-01-13

Added:

- From FIT files we also extract the _grade_, _temperature_ and _GPS accuracy_ fields if they are present. There is no analysis for them yet, though. Also extract the workout name, sport and sub-sport fields from FIT files. [GH-81](https://github.com/martin-ueding/geo-activity-playground/pull/81)
- Add more logging to diagnose Unicode issue on macOS. [GH-83](https://github.com/martin-ueding/geo-activity-playground/issues/83)

Changed:

- Use locally downloaded tiles for all maps, this way we do not need to download them twice for activities and explorer/heatmap.
- Localize SimRa files to local time zone. [GH-80](https://github.com/martin-ueding/geo-activity-playground/pull/80)
- Parse speed unit from FIT file. There are many devices which record in m/s and not in km/h, yielding too low speeds in the analysis. This is now fixed. [GH-82](https://github.com/martin-ueding/geo-activity-playground/pull/82)
- Skip `.DS_Store` files in the activity directory. [GH-81](https://github.com/martin-ueding/geo-activity-playground/pull/81)

## Version 0.17.0 — 2024-01-03

Added:

- Add `Dockerfile` such that one can easily use this with Docker. [GH-78](https://github.com/martin-ueding/geo-activity-playground/pull/78)
- Add support for the CSV files of the [SimRa Project](https://simra-project.github.io/). [GH-79](https://github.com/martin-ueding/geo-activity-playground/pull/79)

Fixed:

- Fix bug which broke the import of `.tcx.gz` files.

## Version 0.16.4 — 2023-12-23

Fixed:

- Fix syntax error.

## Version 0.16.3 — 2023-12-23

Changed:

- Ignore Strava activities without a time series.

## Version 0.16.2 — 2023-12-22

Changed:

- Make heatmap images that are downloaded look the same as the interactive one.
- Always emit the path when there is something wrong while parsing an activity file.

## Version 0.16.1 — 2023-12-22

Fixed:

- Fix handling of TCX files on Windows. On that platform one cannot open the same file twice, therefore my approach failed. Now I close the file properly such that this should work on Windows as well.

## Version 0.16.0 — 2023-12-22

Added:

- Add feature to render heatmap from visible area. [GH-73](https://github.com/martin-ueding/geo-activity-playground/issues/73)
- Add offsets for equipment. [GH-71](https://github.com/martin-ueding/geo-activity-playground/issues/71)
- Add action to convert Strava checkout to our format. [GH-65](https://github.com/martin-ueding/geo-activity-playground/issues/65)
- Add simple search function. [GH-70](https://github.com/martin-ueding/geo-activity-playground/issues/70)

Fixed:

- Fix number of tile visits in explorer view. [GH-69](https://github.com/martin-ueding/geo-activity-playground/issues/69)
- Filter out some GPS jumps. [GH-54](https://github.com/martin-ueding/geo-activity-playground/issues/54)

Removed:

- Remove heatmap image generation from clusters, remove Scikit-Learn dependency.

## Version 0.15.3 — 2023-12-20

Fixed:

- Create temporary file for TCX parsing in the same directory. There was a problem on Windows where the program didn't have access permissions to the temporary files directory.

## Version 0.15.2 — 2023-12-20

Fixed:

- Try to open GPX files in binary mode to avoid encoding issues. [GH-74](https://github.com/martin-ueding/geo-activity-playground/issues/74)

## Version 0.15.1 — 2023-12-16

Fixed:

- Add `if __name__ == "__main__"` clause such that one can use `python -m geo_activity_playground` on Windows.

## Version 0.15.0 — 2023-12-13

Changed:

- Export all missing tiles in the viewport, not just the neighbors.
- Automatically retry Strava API when the rate limit is exhausted. [GH-67](https://github.com/martin-ueding/geo-activity-playground/pull/67)

Fixed:

- Give more helpful error messages when the are no activity files present.

## Version 0.14.2 — 2023-12-12

Fixed:

- Fix broken Strava import (bug introduced in 0.14.0).

## Version 0.14.1 — 2023-12-12

Fixed:

- Fix hard-coded part in KML import (bug introduced in 0.14.0).

## Version 0.14.0 — 2023-12-12

Added:

- Allow setting host and port via the command line. [GH-61](https://github.com/martin-ueding/geo-activity-playground/pull/61)
- Re-add download of explored tiles in area. [GH-63](https://github.com/martin-ueding/geo-activity-playground/issues/63)
- Add some sort of KML support that at least works for KML exported by Viking. [GH-62](https://github.com/martin-ueding/geo-activity-playground/issues/62)

Changed:

- Do more calculations eagerly at startup such that the webserver is more responsive. [GH-58](https://github.com/martin-ueding/geo-activity-playground/issues/58)
- Unify time handling, use UTC for all internal representations. [GH-52](https://github.com/martin-ueding/geo-activity-playground/issues/52)

## Version 0.13.0 — 2023-12-10

Added:

- Add cache migration functionality.
  - Make sure that cache directory is created beforehand. [GH-55](https://github.com/martin-ueding/geo-activity-playground/issues/55)
- Split tracks into segments based on gaps of 30 seconds in the time data. That helps with interpolation across long distances when one has paused the recording. [GH-47](https://github.com/martin-ueding/geo-activity-playground/issues/47)
  - Fix introduced bug. [GH-56](https://github.com/martin-ueding/geo-activity-playground/issues/56)
- Add cache to heatmap such that it doesn't need to render all activities and only add new activities as needed.
- Add a footer. [GH-49](https://github.com/martin-ueding/geo-activity-playground/issues/49)

Changed:

- Revamp heatmap, use interpolated lines to provide a good experience even at high zoom levels.
  - This also fixes the gaps that were present before. [GH-34](https://github.com/martin-ueding/geo-activity-playground/issues/34)
- Only export missing tiles in the active viewport. [GH-53](https://github.com/martin-ueding/geo-activity-playground/issues/53)

Fixed:

- Add missing dependency to SciKit Learn again; I was too eager to remove that. [GH-59](https://github.com/martin-ueding/geo-activity-playground/issues/59)

## Version 0.12.0 — 2023-12-07

Changed:

- Change coloring of clusters, have a color per cluster. Also mark the square just as an overlay.

Fixed:

- Fix bug with explorer tile page when the maximum cluster or square is just 1. [GH-51](https://github.com/martin-ueding/geo-activity-playground/issues/51)
- Speed up the computation of the latest tiles.

## Version 0.11.0 — 2023-12-03

Added:

- Add last activity in tile to the tooltip. [GH-35](https://github.com/martin-ueding/geo-activity-playground/issues/35)
- Add explorer coloring mode by last activity. [GH-45](https://github.com/martin-ueding/geo-activity-playground/issues/45)
- Actually implement `Activity/{Kind}/{Equipment}/{Name}.{Format}` directory structure.
- Document configuration file.
- Show time evolution of the number of explorer tiles, the largest cluster and the square size. [GH-33](https://github.com/martin-ueding/geo-activity-playground/issues/33)
- Show speed distribution. [GH-42](https://github.com/martin-ueding/geo-activity-playground/issues/42)

Changed:

- Interpolate tracks to find more explorer tiles. [GH-27](https://github.com/martin-ueding/geo-activity-playground/issues/27)
- Center map view on biggest explorer cluster.

Fixed:

- Fix bug that occurs when activities have no distance information.

## Version 0.10.0 — 2023-11-27

Changed:

- Use a grayscale map for the explorer tile maps. [GH-38](https://github.com/martin-ueding/geo-activity-playground/issues/38)
- Explicitly write “0 km” in calendar cells where there are no activities. [GH-39](https://github.com/martin-ueding/geo-activity-playground/issues/39), [GH-40](https://github.com/martin-ueding/geo-activity-playground/pull/40)

## Version 0.9.0 — 2023-11-26

Added:

- Support TCX files. [GH-8](https://github.com/martin-ueding/geo-activity-playground/issues/8)

Changed:

- Certain exceptions are not skipped when parsing files. This way one can gather all errors at the end. [GH-29](https://github.com/martin-ueding/geo-activity-playground/issues/29)

Fixed:

- Fix equipment view when using the directory source. [GH-25](https://github.com/martin-ueding/geo-activity-playground/issues/25)
- Fix links from the explorer tiles to the first activity that explored them. [GH-30](https://github.com/martin-ueding/geo-activity-playground/issues/30)
- Fix how the API response from Strava is handled during the initial token exchange. [GH-37](https://github.com/martin-ueding/geo-activity-playground/issues/37)

## Version 0.8.3 — 2023-11-26

Changed:

- Only compute the explorer tile cluster size if there are cluster tiles. Otherwise the DBSCAN algorithm doesn't work anyway. [GH-24](https://github.com/martin-ueding/geo-activity-playground/issues/24)
- Remove allocation of huge array. [GH-23](https://github.com/martin-ueding/geo-activity-playground/issues/23)

## Version 0.8.2 — 2023-11-26

Fixed:

- Some FIT files apparently have entries with explicit latitude/longitude values, but those are null. I've added a check which skips those points.

## Version 0.8.1 — 2023-11-26

Fixed:

- Fix reading of FIT files from Wahoo hardware by reading them in binary mode. [GH-20](https://github.com/martin-ueding/geo-activity-playground/issues/20).
- Fix divide-by-zero error in speed calculation. [GH-21](https://github.com/martin-ueding/geo-activity-playground/issues/21)

## Version 0.8.0 — 2023-11-26

Added:

- Compute explorer cluster and square size, print that. [GH-2](https://github.com/martin-ueding/geo-activity-playground/issues/2)

Changed:

- Make heart rate zone computation a bit more flexibly by offering a lower bound for the resting heart rate.
- Open explorer map centered around median tile.
- Make it compatible with Python versions from 3.9 to 3.11 such that more people can use it. [GH-22](https://github.com/martin-ueding/geo-activity-playground/issues/22)

## Version 0.7.0 — 2023-11-24

Added:

- Add _Squadratinhos_, which are explorer tiles at zoom 17 instead of zoom 14.

Changed:

- Reduce memory footprint for explorer tile computation.

## Version 0.6.0 — 2023-11-24

Added:

- Interactive map for each activity.
- Color explorer tiles in red, green and blue. [GH-2](https://github.com/martin-ueding/geo-activity-playground/issues/2)
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

Changed:

- Directly serve GeoJSON and Vega JSON embedded in the document.
- Automatically detect which source is to be used. [GH-16](https://github.com/martin-ueding/geo-activity-playground/issues/16)
- Fix the name of the script to be `geo-activity-playground` and not just `geo-playground`. [GH-11](https://github.com/martin-ueding/geo-activity-playground/issues/11)

## Version 0.5.0 — 2023-11-15

Added:

- Add some plots for the Eddington number. [GH-3](https://github.com/martin-ueding/geo-activity-playground/issues/3)

## Version 0.4.0 — 2023-11-10

Added:

- Add some more plots.

## Version 0.3.0 — 2023-11-10

Added:

- Start to build web interface with Flask.
- Add interactive explorer tile map.

Removed:

- Remove tqdm progress bars and use colorful logging instead.

## Version 0.2.0 — 2023-11-05

Added:

- Export missing tiles as GeoJSON.
- Add Strava API.
- Add directory source.

Changed:

- Unify command line entrypoint.
- Crop heatmaps to fit.

## Version 0.1.3 — 2023-07-28

Added:

- Generate some heatmap images.
- Generate an explorer tile video.

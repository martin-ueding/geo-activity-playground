# Changelog

This is the log of high-level changes that I have done in the various versions.

## Version 0

This is the pre-release series. Things haven't settled yet, so each minor version might introduce breaking changes.

### Version 0.11

- Add last activity in tile to the tooltip. [GH-35](https://github.com/martin-ueding/geo-activity-playground/issues/35)
- Add explorer coloring mode by last activity. [GH-45](https://github.com/martin-ueding/geo-activity-playground/issues/45)
- Actually implement `Activity/{Kind}/{Equipment}/{Name}.{Format}` directory structure.

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
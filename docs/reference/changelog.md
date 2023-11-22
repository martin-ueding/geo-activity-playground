# Changelog

This is the log of high-level changes that I have done in the various versions.

## Version 0

This is the pre-release series. Things haven't settled yet, so each minor version might introduce breaking changes.

### Version 0.6

- Interactive map for each activity.
- Color explorer tiles in red, green and blue.
- Directly serve GeoJSON and Vega JSON embedded in the document.
- Automatically detect which source is to be used.
- Fix the name of the script to be `geo-activity-playground` and not just `geo-playground`.
- Add mini maps to the landing page.
- Add fullscreen button to the maps.
- Add favicon.
- Added some more clever caching to the explorer tiles such that loading the page with explorer tiles comes up in just a few seconds.
- Add a triplet of time series plots (distance, altitude, heart rate) for each activity.

### Version 0.5

- Add some plots for the Eddington number.

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
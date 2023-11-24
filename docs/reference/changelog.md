# Changelog

This is the log of high-level changes that I have done in the various versions.

## Version 0

This is the pre-release series. Things haven't settled yet, so each minor version might introduce breaking changes.

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
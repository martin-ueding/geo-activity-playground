# Using Activity Files

Outdoor activities are usually recorded as `.GPX` or `.FIT` files. Some apps like [OsmAnd](https://osmand.net/) , [OpenTracks](https://opentracksapp.com/) or [Organic Maps](https://organicmaps.app/), GPS handhelds, smartwatches or cycling computers give you these files.

## Supported file formats

- FIT
- GPX
- TCX
- KML
- KMZ
- [Simra](https://www.digital-future.berlin/forschung/projekte/simra/) CSV export

## Add Activity Files

Before starting the service you need to create a folder for your activities and put at least one activity file in there.

Create a `Playground` folder on your storage somewhere and add a subfolder `Activities`. There you can add your activity files.
For example:

```
~/
├─ Documents[or other location]/
│  ├─ Playground/
│  │  ├─ Activities/
│  │  │  ├─ 2024-03-03-17-42-10 Home to Bakery.gpx
```

The program will treat the files as read-only and does not modify them.

Once the service is running you can use the [Uploader](https://martin-ueding.github.io/geo-activity-playground/features/upload/) to add your files.
You can manually rename, move or delete your activity files, but the program needs to reload to respect these changes.
You can restart the program or visit `Scan New Activities` in the admin menu of the WebUI.

## Metadata extraction

Most activity file formats contain basic data like `date`, `time` and `track points`. Each activity in geo-activity-playground also has the metadata fields `kind`, `equipment` and `name`. They can be extracted from files that contain them.

If no metadata is found, `kind` and `equipment` default to `Unknown`. The `name` is then extracted from the file name (without the suffix).
So for `Activities/2024-03-03-17-42-10 Home to Bakery.gpx` the `name` is `2024-03-03-17-42-10 Home to Bakery`.

## Next steps

Once you have your files put into the directory, you're all set and can proceed with the next steps.

You can extend the directory structure to categorize your activities, see [Advanced Metadata Extraction](https://martin-ueding.github.io/geo-activity-playground/getting-started/advanced-metadata-extraction).

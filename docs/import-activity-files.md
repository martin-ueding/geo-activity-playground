# Import Activity Files

One way to get your activities into Geo Activity Playground is by adding files to a directory in your base directory. See the options to [record activities](record-activities.md).

This how-to assumes that you have a way to record activities and transfer them to your computer.

## Supported file formats

The supported file formats are the following:

- GPX: Widely spread format.
- FIT: Format by Garmin, used by various fitness devices.
- KML, KMZ: Default with Google Earth
- TCX
- [Simra](https://www.digital-future.berlin/forschung/projekte/simra/) CSV

## Add activity files on the file system

Inside of your [base directory](create-a-base-directory.md), create a directory named `Activities` for your activities. Put your files there. If you want, you can have an arbitrary directory structure within that, just the uppermost directory needs to have the fixed name.

The program will treat the files as read-only and does not modify them.

You can manually rename, move or delete your activity files, but the program needs to reload to respect these changes. You can restart the program or visit “Scan New Activities” in the admin menu of the web interface.

## Metadata extraction

Most activity file formats contain basic data like `date`, `time` and `track points`. Each activity in geo-activity-playground also has the metadata fields `kind`, `equipment` and `name`. They can be extracted from files that contain them.

If no metadata is found, `kind` and `equipment` default to `Unknown`. The `name` is then extracted from the file name (without the suffix).
So for `Activities/2024-03-03-17-42-10 Home to Bakery.gpx` the `name` is `2024-03-03-17-42-10 Home to Bakery`.

## Next steps

Once you have your files put into the directory, you're all set and can proceed with the next steps.

You can extend the directory structure to categorize your activities, see [advanced metadata extraction](advanced-metadata-extraction.md).

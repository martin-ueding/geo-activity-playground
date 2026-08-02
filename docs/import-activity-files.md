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

## Upload files through the web interface

Instead of copying files yourself, you can upload them under “Upload Activity” in the admin menu. You can select several files at once.

If a file with the same name is already there, the upload is stored under the SHA-256 checksum of its content instead. If the content is identical to a file that is already there, the upload is skipped, because it would be a duplicate anyway.

After the import you land on a bulk edit page that shows one entry per uploaded activity with a small map, so you can check what was imported and correct the metadata right away. Name, description, kind, equipment and tags are editable there; for everything else follow the “All fields” link to the activity edit page.

### Where the name comes from

Devices are not consistent about where they put the activity name. Some write it into the file, others encode it only in the file name. The bulk edit page therefore shows both candidates for each activity and offers two buttons at the top that fill in all rows at once, either from the activity file or from the file name. The same applies to the activity kind. Nothing is saved until you press Save, so you can switch back and forth and correct individual rows.

At import time the [metadata extraction regexes](advanced-metadata-extraction.md) still take precedence over what the file says. The values found inside the file are recorded alongside, which is what lets the bulk edit page offer them afterwards. This only happens for newly imported activities; existing ones have no record of what their file said.

## Next steps

Once you have your files put into the directory, you're all set and can proceed with the next steps.

You can extend the directory structure to categorize your activities, see [advanced metadata extraction](advanced-metadata-extraction.md).

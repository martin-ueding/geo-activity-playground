# Using Activity Files

Outdoor activities are usually recorded as GPX or FIT files. Some apps like OsmAnd give you these files.

Create a directory somewhere, this will be your _playground_. I have mine in `~/Dokumente/Karten/Playground`, but you can put yours wherever you would like.

Inside `Playground`, create another directory `Activities`. You can create an arbitrary directory structure below that, at the moment it doesn't have any meaning. I do plan to give it meaning at some point and think about a structure like `Playground/Activities/{Activity Type}/{Equipment}/{year}-{month}-{day}-{hour}-{minute}-{name}.gpx`. Then the _activity type_ would be things like _ride_, _run_, _walk_, _hike_. The equipment would be the name for bikes or shoes such that one can aggregate distances per equipment. Perhaps one could add another subdirectory `Commute` such that all the repetitive commutes could go into there.

Either way, at the moment we only really need `Playground/Activities/{name}.gpx` (or `.fit`).

Once you have your files there, you can proceed with the next steps.

When starting the program, you need to supply the argument `--source directory` to select the activity files as your source.
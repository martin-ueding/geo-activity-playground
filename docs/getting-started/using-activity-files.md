# Using Activity Files

Outdoor activities are usually recorded as GPX or FIT files. Some apps like OsmAnd give you these files.

Create a directory somewhere, this will be your _playground_. I have mine in `~/Dokumente/Karten/Playground`, but you can put yours wherever you would like.

Inside `Playground`, create another directory `Activities` where your activity files will go. You will need to put at least one activity file in there, otherwise the program cannot start. The program will not modify files in that directory and treat them as read-only.

## Directory structure

Some activity file formats contain metadata. You can also add metadata via the file name and by putting into a directory. By default only the stem of the path (the part without the suffix) will be used to derive the name of the activity. If you want, you can use a naming and directory structure to fill in more meta data using regular expressions.

Each activity has the metadata fields `kind`, `equipment` and `name`. The kind and equipment are extracted from the activity file. If there nothing is found, it defaults to “Unknown”. Using a regular expression with named capture groups one can extract these fields also from the files. I for instance have the following file paths:

- `Ride/Trekking Bike/Home to Bakery/2024-03-03-17-42-10.fit`
- `Hike/Hiking Boots 2019/2024-03-03-11-03-18 Some nice place with Alice and Bob.fit`

My structure is built such that the first directory level corresponds to the activity kind. The second level is the equipment used. Unique activities are directly in there as files. But there can also be a directory for the name and then just files with only the date as name. This way I can just put a lot of similar commutes there without having to name the files. In the first example I want it to take the name from the third directory. In either case I don't want to have the date to be part of the name.

In order to extract this data, I specify a list of regular expressions with named capture groups like `(?P<name>…)` where `name` is the field that you want to populate and `…` some regular expression. The program will try to _search_ (not _match_) the whole relative path of the activity to the regular expressions in the order given in the list. When it finds a match, it will take the capture groups, populate the metadata and stop evaluating more of the expressions. In my case they look like this:

```
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/]+)/
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ ]+(?P<name>[^/]+)(?:\.\w+)+$
(?P<kind>[^/]+)/[-\d_ ]+(?P<name>[^/]+)(?:\.\w+)+$
```

Put something like that at the top of your `config.toml` in order to extract metadata from the files and have it override metadata from the within the files.

## Supported file formats

At the moment the following file formats are supported:

1. FIT
2. GPX
3. TCX

## Next steps

Once you have your files put into the directory, you're all set and can proceed with the next steps.
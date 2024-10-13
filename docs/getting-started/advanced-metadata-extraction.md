# Advanced Metadata extraction

If you would like to set the metadata fields or change what part of the filename should be the activity name, you can use a custom directory structure with corresponding regular expressions.

An example directory structure:

```
Activities/
├─ Ride/
│  ├─ Trekking Bike/
│  │  ├─ 2024-03-03-17-42-10 Home to Bakery.gpx
├─ Hike/
│  ├─ Hiking Boots 2019/
│  │  ├─ 2024-03-03-11-03-18 Some nice place with Alice and Bob.fit
```

## Custom Regular expressions

The program uses regular expressions to search for patterns in the relative path (in Activities) and extracts the relevant parts with named capture groups `(?P<kind>)`, `(?P<equipment>)`, `(?P<name>)`.

You can use python to test your regular expressions. Read the [python re documentation](https://docs.python.org/3/library/re.html) for some help.

```
import re
re.search(r'(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/.]+)', '/Ride/Trekking Bike/2024-03-03-17-42-10 Home to Bakery.gpx').groupdict()

{'kind': 'Ride', 'equipment': 'Trekking Bike', 'name': '2024-03-03-17-42-10 Home to Bakery'}
```

You can add your custom regular expressions under the `Admin` menu - `Settings` - `Metadata Extraction` in the WebUI.
Settings are saved in your `Playground` directory.

### Filename as Name (simple)

Path:

```
Activities/
├─ Ride/
│  ├─ Trekking Bike/
│  │  ├─ 2024-03-03-17-42-10 Home to Bakery.gpx
```

```
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/.]+)
```

- kind = `Ride`
- equipment = `Trekking Bike`
- name = `2024-03-03-17-42-10 Home to Bakery`

### Filename without date as Name (useful for OsmAnd naming)

Path:

```
Activities/
├─ Ride/
│  ├─ Trekking Bike/
│  │  ├─ 2024-03-03-17-42-10 Home to Bakery.gpx
│  │  ├─ 2024-03-04-16-52-26.gpx
│  │  ├─ 2024-04-21_10-28_Sun OsmAnd default track.gpx
│  │  ├─ 2024-04-22_07-55_Mon.gpx
```

```
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/[-\d_ ]+(?P<name>[^/]+)(?:\.\w+)+$
```

- kind = `Ride`
- equipment = `Trekking Bike`
- names = `Home to Bakery` ; ` ` ; `Sun OsmAnd default track` ; `Mon`

Attention, name may be empty if it is not included in the file name.
For OsmAnd default naming the weekday is included in the name.

### Filename after first space as Name

Path:

```
Activities/
├─ Ride/
│  ├─ Trekking Bike/
│  │  ├─ 2024-03-03-17-42-10 Home to Bakery.gpx
│  │  ├─ 2024-04-22_07-55_Mon.gpx
│  │  ├─ 2024-04-21_10-28_Sun OsmAnd default track.gpx
```

```
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/\S+ ?(?P<name>[^/\.]*)
```

- kind = `Ride`
- equipment = `Trekking Bike`
- names = `Home to Bakery` ; ` ` ; `OsmAnd default track`

Attention, name may be empty if it is not included in the file name (also for OsmAnd default naming).

### Grouping activity files under a common name, for example all your commutes

Path:

```
Activities/
├─ Ride/
│  ├─ Trekking Bike/
│  │  ├─ Commute/
│  │  │  ├─ 2024-03-04-07-06-12.gpx
│  │  │  ├─ 2024-03-04-15-42-32.gpx
```

```
(?P<kind>[^/]+)/(?P<equipment>[^/]+)/(?P<name>[^/]+)/
```

- kind = Ride
- equipment = Trekking Bike
- name = Commute (for all activities in Commute directory )

### Activities without equipment

Path:

```
Activities/
├─ Run/
│  ├─ 2024-03-09-09-24-03 To the lake.gpx
│  ├─ 2024-03-10-09-44-37 To the top of the hill.gpx
```

```
(?P<kind>[^/]+)/[-\d_ ]+(?P<name>[^/]+)(?:\.\w+)+$
```

- kind = Run
- equipment = Unknown
- names = To the lake , To the top of the hill

## Next Steps

If you you manually rename, move or delete your activity files, the program needs to reload to respect these changes.
You can restart the program or visit `Scan New Activities` in the admin menu of the WebUI.
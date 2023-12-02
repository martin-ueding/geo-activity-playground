# Using Activity Files

Outdoor activities are usually recorded as GPX or FIT files. Some apps like OsmAnd give you these files.

Create a directory somewhere, this will be your _playground_. I have mine in `~/Dokumente/Karten/Playground`, but you can put yours wherever you would like.

Inside `Playground`, create another directory `Activities` where your activity files will go. The program will not modify files in that directory and treat them as read-only.

## Directory structure

Inside the `Activities` you can dump all your files in a flat fashion. If you want to add some more metadata, use the following directory layout.

The first directory level will indicate the type of the activity. You can pick whatever make sense for you, classic options are _ride_, _run_, _walk_, _hike_. Then the second level will indicate your equipment. You can use terms like “rental bike”, the brand and make of your shoes or whatever you find sensible. Specifying the equipment allows to track the total distance traveled with a given equipment.

At any level you can have a special directory `Commute`. All activities inside of that will be marked as commutes and not highlighted as much as non-commute activities. The idea is that you can find your cool activities along potentially many commutes.

Other directory names on the third level will just be ignored, you can use those to organize your activities further in some sense.

Let us take the following directory/file structure as an example:

```
Activities
├── Commute
│   └── From the Beach.gpx
├── Ride
│   └── Rental Bike
│       ├── Beach Rides
│       │   └── Breskens.gpx
│       └── Zwin.gpx
├── To Piazza.gpx
└── Walk
    ├── Commute
    │   └── To the Beach.gpx
    ├── New Balance Fresh Foam 860v11
    │   ├── Beach Walk.gpx
    │   └── Commute
    │       └── From Piazza.gpx
    └── Nieuvfliet.gpx
```

You can see that I have one file on the top level (`To Piazza.gpx`), a file on the first level (`Walk/Nieuvfliet.gpx`), some on the second level (`Ride/Rental Bike/Zwin.gpx`), one commute (`Walk/New Balance Fresh Foam 860v11/Commute/From Piazza.gpx`) and one with a group directory which isn't commuting (`Ride/Rental Bike/Dunes in Sluis/Breskens.gpx`). From this the program will extract the following metadata:

Name | Type | Equipment | Commute
--- | --- | --- | ---
From the Beach | _None_ | _None_ | Yes
Breskens | Ride | Rental Bike | No
Zwin | Ride | Rental Bike | No
To Piazza | _None_ | _None_ | No
To the Beach | Walk | _None_ | Yes
Beach Walk | Walk | New Balance Fresh Foam 860v11 | No
From Piazza | Walk | New Balance Fresh Foam 860v11 | Yes
Nieuwvliet | Walk | _None_ | No

The file name of your activity will become the name of the activity.

## Supported file formats

At the moment the following file formats are supported:

1. FIT
2. GPX
3. TCX

## Next steps

Once you have your files put into the directory, you're all set and can proceed with the next steps.
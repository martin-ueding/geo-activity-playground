# Configuration file

The project tries to adhere to the _convention over configuration_ mantra and therefore minimizes the amount of configuration necessary. There are still a few data points which one might need to fill out. This page summarizes all the configuration file elements and links to the features that use them.

The configuration file is optional. If you want to create one, it needs to be placed at `Playground/config.toml`. The configuration file is in the [TOML format](https://toml.io/en/) and contains multiple _tables_ with options. We will go through them here one-by-one.

## Strava API

If you want to use the Strava API, see the [Strava API page](using-strava-api.md) first. There you can read how to find the values; the configuration snippet is this:

```toml
[strava]
client_id = "…"
client_secret = "…"
code = "…"
```

## Heart rate

In order to use the [heart rate zone feature](../features/activity-view.md#heart-rate-zones), you will need to somehow specify your maximum and minimum heart rate.

In order to specify the maximum heart rate, either specify your `birthyear` and it will estimate it from that. Or specify the `maximum` heart rate instead. For the minimum you can optionally specify the `resting` heart rate. If you leave that empty, the minimum will be taken as 0, which is how Garmin also computes the zones.

This is an example configuration:

```toml
[heart]
# Specify either `birthyear` or `maximum`:
birthyear = 19..
## maximum = 187

# Optionally specify `resting`:
## resting = 48
```

## Equipment offsets

Perhaps you haven't recorded every single activity with an equipment but still know what the offset is. For me it is my trekking bike which I bought and used with a plain bike mounted odometer. Only after some time I've started to record all activities. I know that the offset is 3850 km, so I'd like to add that to my equipment overview. For this one can specify another block in the configuration:

```toml
[offsets]
"Trekkingrad 2019" = 3850
```

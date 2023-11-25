# Activity View

When you have selected a particular activity, you can view various details about it. This is what the screen looks like, we will go through the different parts in the following.

![](activity-overview.png)

## Metadata

You have a column with metadata about the activity. The activity kind, whether it is a commute and the equipment are currently only supported via the Strava API, but we can build something to infer that from directories as well.

![](activity-meta.png)

The calories are broken in the Strava API wrapper library that I use, therefore they don't show even if they are there.

You can also see the ID which is an internal ID.

## Map with track

![](activity-map.png)
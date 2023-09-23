# Heatmaps

From all the points in your activities, one can generate nice heatmaps. This builds on the [Strava local heatmap code](https://github.com/remisalmon/Strava-local-heatmap).

We don't generate a single heatmap for all your activities as this will not look great as soon as you have done an activity away from home. Rather we use a clustering algorithm to find all disjoint geographical clusters in your activities and generate one heatmap per cluster.

For instance the heatmap generated from all my activities in the [Randstad](https://en.wikipedia.org/wiki/Randstad) in the Netherlands:

![](heatmap-randstad.png)
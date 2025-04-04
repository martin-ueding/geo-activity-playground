# Home

Geo Activity Playground is a software to view recorded outdoor activities and derive various insights from your data collection. All data is kept on your machine, hence it is suitable for people who have an affinity for data analysis and privacy.

It caters to serve a similar purpose as other systems like [Strava](https://strava.com/), [Statshunters](https://statshunters.com/) or [VeloViewer](https://veloviewer.com/), though the focus here is on self-hosting and using local files.

One can use this program with a local collection of activity files (GPX, FIT, TCX, KML, CSV) or via the Strava API. The latter is appealing to people who want to keep their data with Strava primarily. In case that one wants to move, this might provide a noncommittal way of testing out this project.

The main user interface is web-based, you can run this on your Linux, Mac or Windows laptop. If you want, it can also run on a home server or your personal cloud instance.

## Screenshot tour

This is the view of a single activity:

![](images/screenshot-activity.png)

You also get a beautiful interactive heatmap of all your activities:

![](images/screenshot-heatmap.png)

Also there are plenty of summary statistics that lets you track how many rides, walks or hikes you have done:

![t](images/screenshot-summary.png)

If you're into _explorer tiles_ or _squadratinhos_, this got you covered:

![](images/screenshot-explorer.png)

The configuration options are available within the interface such that you do not have to work with configuration files (like in earlier versions):

![](images/screenshot-settings.png)

## Get started

If you're new, just follow these steps:

1. Install the software on [Linux](install-on-linux.md), [Windows](install-on-windows.md) or [macOS](install-on-macos.md).
2. [Create a base directory](create-a-base-directory.md).
3. [Start the webserver](starting-the-webserver.md).
4. Choose a method to [record activities](record-activities.md).
5. Import your activities via [activity files](import-activity-files.md), [connect the Strava API](connect-strava-api.md) or [upload activity files](upload-activity-files.md) in the web interface.

Have fun. If you're stuck, [get help](get-help.md).

## Free software

You can [find the code on GitHub](https://github.com/martin-ueding/geo-activity-playground) where you can also file issues. If you would like to use this yourself or contribute, feel free to reach out via the contact options [from my website](https://martin-ueding.de/). I would especially appreciate improvements to the documentation. If you're familiar with Markdown and GitHub, you can also directly create a pull request. The code is licensed under the very permissive MIT license.
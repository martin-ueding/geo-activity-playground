# Connect Strava API

!!! tip "When to use this guide"
    Use this guide if you **want to keep using Strava** as your primary platform and have Geo Activity Playground sync from it automatically.
    
    - You want to continue recording with the Strava app.
    - You want new activities to sync automatically.
    - You're okay with your data living on Strava's servers.
    
    **Not for you?**
    
    - If you want to **stop using Strava entirely**, see [Moving from Strava](moving-from-strava.md) instead.
    - If you have **local GPX/FIT files** (not from Strava), see [Import activity files](import-activity-files.md).

You might have all your data on the Strava service and would like to use this for additional analytics without moving your data. That is fine.

If you don't mind a bit of rate-limiting, you can just directly go ahead and start the webserver. It will offer to connect with Strava.

## Your own Strava App

In order to use the Strava API without sharing the rate-limiting with other users, you need to create your own app. If my explanation doesn't suit you, have a look [at this how-to guide](https://towardsdatascience.com/using-the-strava-api-and-pandas-to-explore-your-activity-data-d94901d9bfde) as well.

Navigate to the [API settings page](https://www.strava.com/settings/api) and create an app. It only needs to have read permissions.

After you are done with that, you can see your App here:

![](images/strava-api-2.png)

There is a "client ID" and a "client secret" that we are going to need for the next step. In general our app could be used by all sorts of people who can then access _their_ data only. We want to access our own data, but we still need to authorize our app to use our data. 

Open the webserver of this program and go the Strava API setup page. Enter your client ID and client secret, click on "Connect to Strava".

This will prompt an OAuth2 request where you have to grant permissions to your app. After that you will be redirected back to the app and it should be set up. At the moment you need to restart the webserver such that it can start to download the activities. Due to rate-limiting it can still take a while.

## Use export to avoid rate limiting

When you first start this program and use the Strava API as a data source, it will download the metadata for all your activities. Then it will start to download all the time series data for each activity. Strava has a rate limiting, so after the first 200 activities it will crash and you will have to wait for 15 minutes until you can try again and it will download the next batch.

Therefore it is recommended to use a Strava export in order to get started quicker. For this go to the [Strava account download page](https://www.strava.com/athlete/delete_your_account) and download all your data. You will get a ZIP file. Unpack the files into `Playground/Strava Export`. These will be picked up there. Activities from Strava will only be downloaded after importing all these, and only the ones after the last one in the export will be downloaded. This way you can get started much quicker.

!!! warning "This is NOT the same as moving from Strava"
    This `Strava Export/` folder is specifically for **speeding up the initial Strava API sync**. It does not convert or process your files — it's just a cache to avoid rate limiting.
    
    - Do **not** put these files in your `Activities/` folder.
    - If you want to **leave Strava entirely**, see [Moving from Strava](moving-from-strava.md) instead.

## Skip Strava download

If you don't want to download new activities from Strava, use `--skip-reload` to have the webserver start right away.

## Rescan all Strava activities

The scanning of Strava activities resumes after the last activity that was imported. If you want to override this behavior temporarily, you can add `--strava-begin YYYY-MM-DD` and/or `--strava-end YYYY-MM-DD` at the end of the command line (after `serve`). Replace the placeholders with a date like 2025-07-13. This will trigger a scan of Strava activities within the specified time range.
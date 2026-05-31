# Moving from Strava

If you have been using Strava up to this point but want to use this project _exclusively_ from now on, this is the correct guide. Here I will show how you can convert your data from Strava into the format of this project and keep adding new data without Strava in the future.

## Download your archive from Strava

Go to the [Strava account download page](https://www.strava.com/athlete/delete_your_account) and request a download of your data. This will take a while and you get a notification via e-mail when it is done.

Once it has run through, you will be able to download a ZIP file. Once extracted, it will have a structure like this:

```
.
├── activities  [2217 entries exceeds filelimit, not opening dir]
├── activities.csv
├── applications.csv
├── bikes.csv
├── blocks.csv
├── categories_of_personal_information_we_collect.pdf
├── clubs
├── clubs.csv
├── comments.csv
├── community_content.json
├── community_personal_data.json
├── components.csv
├── connected_apps.csv
├── contacts.csv
├── email_preferences.csv
├── events.csv
├── favorites.csv
├── flags.csv
├── followers.csv
├── following.csv
├── general_preferences.csv
├── global_challenges.csv
├── goals.csv
├── group_challenges.csv
├── information_we_disclose_for_a_business_purpose.pdf
├── local_legend_segments.csv
├── logins.csv
├── media  [252 entries exceeds filelimit, not opening dir]
├── media.csv
├── memberships.csv
├── messaging.json
├── metering.csv
├── mobile_device_identifiers.csv
├── orders.csv
├── partner_opt_outs.csv
├── posts.csv
├── privacy_zones.csv
├── profile.csv
├── profile.jpg
├── reactions.csv
├── routes
│   └── 1.gpx
├── routes.csv
├── segments.csv
├── shoes.csv
├── social_settings.csv
├── starred_routes.csv
├── starred_segments.csv
├── support_tickets.csv
└── visibility_settings.csv
```

This directory contains a file `activities.csv` with the metadata and also a directory `activities` with the files that you have recorded.

## Convert your checkout

Use the following command to create a directory from your Strava actitivies:

```bash
geo-activity-playground convert-strava-checkout ~/Downloads/export_123456/ ~/Documents/Outdoors/Playground
```

This should read through all the activities and create a directory structure with the pattern `~/Documents/Outdoors/Playground/Activities/{Kind}/{Equipment}/{Commute}/{Date} {Time} {Name}.{Suffix}`. For instance one file might be named `Activities/Run/5212701.0/2019-07-09 09-59-25 Around the 北京大学 campus.gpx.gz`.

The equipment might have nonsensical seeming names like `10370891.0`. The problem here is that Strava doesn't export the list of activities with that index. If your equipment doesn't have a nickname, it will just be such a number.

## Use the directory

Now that the files from Strava are converted, consult the [guide on using activity files](import-activity-files.md) to proceed from here.

**⚠️ Don't skip the conversion step**

Do **not** copy the `activities/` folder from your Strava archive directly into the `Activities/` folder. The raw Strava files often have issues (missing metadata, problematic timestamps, etc.) that cause import warnings. The `convert-strava-checkout` command properly processes these files.

## Recording more activities

Now that you don't record via Strava, you will need some other app to [record activities](record-activities.md)..
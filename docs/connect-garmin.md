# Connect Garmin

If you record with a Garmin device, your activities are synced to Garmin Connect. Geo Activity Playground can download them from there as the original FIT files, so you don't have to copy files around.

## How it works

Garmin only offers its official API to approved business partners. Therefore this program uses the unofficial [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library, which logs in like the Garmin Connect mobile app does.

- You log in once with your e-mail, password and, if you have it enabled, the verification code that Garmin sends you.
- The password is **not** stored. Only the session tokens that Garmin hands out are kept in the database. They give access to your Garmin account, so protect your database and the password of the web interface like you would protect the password itself.
- The tokens are refreshed automatically. You only need to log in again if Garmin revokes them.
- For each new activity the original FIT file is downloaded and kept in `Cache/Garmin/FIT/`, next to the summary that Garmin returned. This allows to parse the activities again later without asking Garmin again.

⚠️ This is not an official interface. Garmin can change its login at any time, and that has broken such libraries before. Garmin also limits login attempts, and a login that fails again and again can lock your account for a while. If the login fails, wait before you try again.

## Log in

Open the webserver of this program and go to **Settings → Garmin API**. Enter your e-mail and password. If Garmin asks for a verification code, you will be asked for it on the next page.

The page that asks for the verification code only works if it is served by the same server process as the page before. If you run several workers, it might tell you that the login has expired. In that case, log in on the command line instead:

```bash
geo-activity-playground garmin-login
```

This asks for the e-mail, the password and the verification code, and stores the tokens in the database of your playground.

## Import

After the login, the activities are downloaded whenever the webserver starts, oldest first. The first run downloads everything and can take a while. The import resumes after the last activity that was imported without errors.

If you don't want to download new activities from Garmin, use `--skip-reload` to have the webserver start right away.

## Rescan a time range

If you want to override the resume behavior temporarily, add `--garmin-begin YYYY-MM-DD` and/or `--garmin-end YYYY-MM-DD` at the end of the command line (after `serve`). This scans the activities in the given range, and the resume position stays where it was.

## Activities that are not imported

- Activities that were entered by hand have no file and are skipped.
- Activities without a GPS track, like indoor workouts, are recorded as excluded and not downloaded again.
- If you delete an activity in this program, it will not be imported again. You can undo this in **Settings → Excluded Activities**.

## Duplicates

If you also sync your Garmin activities to Strava, the same activity can arrive via both sources. Turn on the duplicate matching in **Settings → Duplicate Matching** to keep one of them. By default the Garmin file wins over Strava and Hammerhead, because it is the original recording.

## Without the API

You can also do without any login. Export your data from Garmin Connect, or copy the FIT files from your device, and follow [Import activity files](import-activity-files.md).

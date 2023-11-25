# Configuration File

There are not so many things to configure. This page contains the configuration options.

You might also have started to build a configuration file if you're [using the Strava API](using-strava-api.md).

The configuration file is a text file named `config.toml` inside the playground directory.

## Heart rate zones



In your config add this block somewhere:

```toml
[heart]
birthyear = 19..
```

It needs your birthyear insted of your age to compute the heart rate zones relevant for the time of the activity. You might have activities spanning multiple years and the zones change ever so slightly. Also we want them to be stable as you get older, so always using the current age doesn't work.
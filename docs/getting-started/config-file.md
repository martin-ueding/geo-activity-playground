# Configuration File

There are not so many things to configure. This page contains the configuration options.

You might also have started to build a configuration file if you're [using the Strava API](using-strava-api.md).

The configuration file is a text file named `config.toml` inside the playground directory.

## Heart rate zones

There are some common definitions of _heart rate zones_, take for instance [this one by Polar](https://www.polar.com/blog/running-heart-rate-zones-basics/). There are five zones, namely from 50 to 60 %, 60 to 70 %, 70 to 80 %, 80 to 90 % and 90 to 100 % of the maximum heart rate. The maximum heart rate would need to be measured, but taking the formula _220 - age_ will do for most people.

In your config add this block somewhere:

```toml
[heart]
birthyear = 19..
```

It needs your birthyear insted of your age to compute the heart rate zones relevant for the time of the activity. You might have activities spanning multiple years and the zones change ever so slightly. Also we want them to be stable as you get older, so always using the current age doesn't work.
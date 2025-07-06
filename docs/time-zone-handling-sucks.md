# Time Zone Handling Sucks

With an unnerving frequency, the topic of time zones comes up. Let me take you into this rabbit hole of horror, inconsistency and missing features.

## Time zone specifications

The problem with time zones is that they inconsistently recorded. A second problem is that there are two ways of specifying them. These two ways seem equivalent until there is the daylight savings time switchover.

I live in Germany, hence I am always in the “Europe/Berlin” time zone. That doesn't change. But the meaning of that changes twice a year. During winter, we “Europe/Berlin” means “Central European Time” (“CET” in English, “MEZ” in German). The offset to UTC (Coordinated Universal Time) is +0100 then. During summer, Germany switches to “Central European Summer Time”, “CEST” (or “Central European Daylight Time”, “CEDT” in American English; “MESZ” in German). Then the UTC offset is +0200.

To summarize: Germany is always in “Europe/Berlin”, but that might mean +0100 or +0200 depending on the date.

## Conversions

When we have a date and time combined, we can convert “Europe/Berlin” into +0100 or +0200, so that is fine.

Let us take the time of writing, 2025-07-06 10:33:00 in Europe/Berlin. Since we have the date, we can deduct that it is daylight savings time here. Hence we can write this as 2025-07-06 10:33:00 +0200. With that offset we can convert that to UTC and write that as 2025-07-06 08:33:00 +0000.

If I have only the offset, say +0200, I cannot convert that back into a named time zone. I might be able to pick something which makes sense at the moment, but it could either be “Europe/Berlin” in summer or “Europe/Kyiv” in winter. But it could also be “Africa/Cairo” in winter. The problem is that not all countries have the [daylight savings time switchover at the same time](https://en.wikipedia.org/wiki/Daylight_saving_time_by_country). Ukraine and Egypt are in different groups, so for a few weeks in a year, it becomes really important which city/country the time zone is from.

## What do we want?

There are two distinct purposes that a date time record has to provide:

1. In what relation did that event happen in relation to another event?
2. What did the clocks show at the pertinent location at the time?

Say two people take pictures during an event with different cameras. In the end, one wants to sort all pictures chronologically. Then the photo software would have to figure out the absolute time. If one camera reports 2025-07-06 10:33:00 +0200, but the other 2025-07-06 08:33:00 +0000, then it would have to deduce that these are actually at the same time. It can do so, because it has the time zone information attached to it and correctly convert both to UTC and take the difference.

One way to achieve this would be to convert all incoming dates into UTC and only store these. Then everything would be sanitized, all time zone information resolved and there were only UTC times. This is a nice state to be in as one doesn't have to worry about time zones any more.

Except when you want to know what the clocks showed. For instance, the time of writing for this article is 10:33:00 +0200. What this tells you is that I am doing that in the late morning (10:33). But if we converted that to UTC, you would only see 08:33:00 +0000. Sure, if you knew that my local time zone is +0200, you could convert it. But we need to track the information.

And actually, there can be a third question: What did my clock show during that event? Say you live in Helsinki, which is at +0300 during the summer. Then your clock would show 11:33:00 +0300. We can do this conversion from UTC or the local time zone of the event creator. But we need to know the user's time zone.

## In this project

Users in various time zones record outdoor activities with whatever device that they have. When displaying activities, we always want to show the local time of the activity. I have activities in Germany (+0100 or +0200), in Greece (+0300) and China (+0800). I don't care about comparing activity start times, I only care about the local times. Hence the local times is what I want.

But when uploading pictures, we now need to figure out which activity they belong to. And then it becomes very important to figure out how the time of the activity and the time of the photo relate to. Hence we need to be able to convert everything into the same time zone, but it doesn't matter which one.

Storing everything as UTC alone doesn't help, we lose the information about local time. Storing everything just in local time (but without time zone) doesn't allow to convert. It would even lead to ambiguities in case somebody goes for a run during the daylight savings time switchover. Hence the ideal storage would be local time plus time zone.

## Inconsistent data

If everything had a proper time zone (as region or UTC offset) attached, it would be easy. I could convert it to local time and keep track of the time zone. If I need to convert times, I could compute the differences properly.

The problem is that the data that I get comes from various devices and I have no control over the formats. For instance, GPX files by Abvio contain the following:

```xml
<desc>Cyclemeter Row 21. Jun 2025 at 17.41.06</desc>
<time>2025-06-21T15:10:41Z</time>
<trkpt lat="…" lon="…"><ele>137.7</ele><time>2025-06-21T14:41:06Z</time></trkpt>
...
<abvio:startTime>2025-06-21 14:41:06.537</abvio:startTime>
<abvio:startTimeZone>Europe/Helsinki</abvio:startTimeZone>
```

So the standardized fields contain UTC data, but there is a non-standard extension field which contains “Europe/Helsinki”. And it is _not_ meant such that `startTime` is in `startTimeZone`, but rather `startTime` is UTC (although the “Z” is missing) and it should be converted into “Europe/Helsinki”.

This can be resolved, but it annoying. If I just look at the standard field `time`, then I would import that as UTC and assume that the user is in +0000 time zone. All the times will look wrong. The activity is at 17:41, so late afternoon. It would show up as 14:41, so early afternoon.

Something recorded with OsmAnd only shows UTC:

```xml
<time>2017-09-05T15:45:40Z</time>
```

There is no other time zone information present, hence we cannot correct that to +0200.

But Open Tracks records in local time zone with offset:

```xml
<time>2025-06-30T19:46:49.776+02:00</time>
```

So that's usable.

As we see here, the program gets fed data with UTC time stamps but we lack information about the local time. This means that this limitation needs to be cured by offering users to shift their activities by asking for the time zone that they should be in.

## Software limitations

As we've seen above, storing data in their local time zone with the time zone information is the best way. But there is a lot of software which is not time zone aware and can only work with naive times. Ouch.

For the data analysis here I use `datetime64`, which doesn't support time zones in its basic NumPy variant:

> This is a “naive” time, with no explicit notion of timezones or specific time scales — [NumPy Documentation](https://numpy.org/doc/stable/reference/arrays.datetime.html)

So when working with these data types, I need to get rid of the time zone. There are two ways:

1. I can convert everything to UTC and only compute with that. This resolves all conflicts with jumps, but it will make all the times in plots wrong.
2. I use only local times. But then I might run into problems if there have been jumps in the time as the time zone has suddenly changed.

At the moment, the program is written with the second way. I have used the first way, but that was worse.

But Pandas does [support time zones in its `datetime64` type](https://pandas.pydata.org/docs/user_guide/timeseries.html). So that's great.

If we supply time zone aware data to Altair, it will pass that onto Vega and then the Browser will [convert that into the local time zone](https://altair-viz.github.io/user_guide/times_and_dates.html). That's not what I want here, the activity should be displayed in the activity's time zone, not in the viewer's.

On top of this, databases like SQLite have their own time zone and [will convert dates back and forth](https://www.reddit.com/r/flask/comments/1im57ij/sqlalchemy_is_driving_me_nuts/). This doesn't make so much sense because I don't want to convert to the time zone of the database. The database should just store the times in the time zone of that time stamp. Likely that doesn't work, I would have to store the offset myself.
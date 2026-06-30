# Cluster History

Beyond the current state of your [explorer tiles](/explorer-tiles), the Explorer page can replay how your cluster grew over time. This how-to guide covers the interactive history overlay and the time-lapse video export.

## Cluster history overlay

Click **Load Cluster History** on the explorer zoom-level page to fetch the history. A time-cutoff slider then lets you scrub backwards and forwards to replay cluster growth activity by activity. Each activity also shows its own cluster delta: which tiles became cluster tiles for the first time because of it.

The history is loaded on demand (not on page load) to keep the initial map fast for large histories.

## Explorer video export

You can export a time-lapse MP4 of your explorer tile history directly from the Explorer page. Open a zoom-level view and use the **Generate explorer MP4** form to configure width, height, FPS, interpolation, and fade, then start rendering. Once done the file is available for download.

The same export is also available via the CLI:

```bash
geo-activity-playground --basedir YOUR_BASEDIR explorer-video --zoom 14 --video-width 1920 --video-height 1080 --fps 30
```

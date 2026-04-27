# Starting the Program

Once you have installed the program and [created a base directory](create-a-base-directory.md), you will learn how to start the program in this how-to.

On Linux, execute the following in the command line, where you need to replace `YOUR_BASEDIR` with the path to your base directory.

```bash
geo-activity-playground --basedir YOUR_BASEDIR serve
```

Should that fail with “command not found”, you need to [add local bin to path](add-local-bin-to-path.md).

The webserver will start up and give you a bit of output like this:

```
2026-04-11 20:34:09 geo_activity_playground.webui.app INFO Using database file at '/home/mu/nobackup/Testsuite/database.sqlite'.
2026-04-11 20:34:09 alembic.runtime.migration INFO Context impl SQLiteImpl.
2026-04-11 20:34:09 alembic.runtime.migration INFO Will assume non-transactional DDL.
Importing activity files: 100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 2/2 [00:00<00:00, 35.74it/s]
2026-04-11 20:34:09 geo_activity_playground.webui.app INFO Importer thread is done.
2026-04-11 20:34:09 geo_activity_playground.webui.app INFO Starting Waitress server at http://127.0.0.1:5000
2026-04-11 20:34:09 waitress INFO Serving on http://127.0.0.1:5000

```

There might be some more messages about downloading and parsing data. The first startup will take quite some time.

Open <http://127.0.0.1:5000> to open the website in your browser and you will see the user interface.

## Explorer video export

Go to Explorer and open a zoom level page. There is a **Generate explorer MP4** form where you can configure width, height, FPS, interpolation, and fade and then start rendering.

You can also use the CLI:

```bash
geo-activity-playground --basedir YOUR_BASEDIR explorer-video --zoom 14 --video-width 1920 --video-height 1080 --fps 30 --download-workers 16
```

## Setting host and port

In case you don't like the default value of `127.0.0.1:5000`, you can use the optional command line arguments `--host` and `--port` to specify your values.

## Optional: choosing the HTTP server

`serve` uses `--http-server waitress` by default, which is the recommended setting for normal use.

There is also `--http-server werkzeug` if you explicitly want the Werkzeug server (for example while debugging server behavior). Most users can safely ignore this option.
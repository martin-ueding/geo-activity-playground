import pathlib

cache_dir = pathlib.Path("~/.cache/geo-activity-playground").expanduser()
cache_dir.mkdir(exist_ok=True)

import requests

from tests.webserver_wrapper import copy_testdata_to_basedir
from tests.webserver_wrapper import webserver


base = "http://localhost:5005"
urls = [
    "/",
    "/summary/",
    "/calendar/",
    "/calendar/2024/5",
    "/activity/day/2024/5/10",
    "/activity/4120089735679315160",
    "/explorer/14",
    "/explorer/17",
    "/heatmap/",
    "/eddington/",
    "/equipment/",
    "/settings",
]


def test_local_files(tmp_path) -> None:
    copy_testdata_to_basedir("Local Files", tmp_path)
    with webserver(tmp_path) as output:
        for url in urls:
            r = requests.get(base + url)
            print(output.read())
            assert r.ok, url


def test_strava_export(tmp_path) -> None:
    copy_testdata_to_basedir("Strava Export", tmp_path)
    with webserver(tmp_path) as output:
        for url in urls:
            r = requests.get(base + url)
            print(output.read())
            assert r.ok, url

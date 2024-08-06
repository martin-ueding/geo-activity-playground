from tests.webserver_wrapper import webserver


def test_wrapper(tmp_path) -> None:
    with webserver(tmp_path):
        print("Started!")
    print("Done!")

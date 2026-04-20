from geo_activity_playground.webui.app import _without_response_header


def test_without_response_header_removes_all_date_headers() -> None:
    def application(_environ, start_response):
        start_response(
            "200 OK",
            [
                ("Date", "Mon, 06 Apr 2026 05:42:11 GMT"),
                ("Content-Type", "text/plain"),
                ("date", "Mon, 06 Apr 2026 05:42:11 GMT"),
            ],
        )
        return [b"ok"]

    wrapped = _without_response_header(application, "Date")
    captured_headers = []

    def start_response(_status, headers, _exc_info=None):
        captured_headers.extend(headers)
        return None

    wrapped({}, start_response)

    assert captured_headers == [("Content-Type", "text/plain")]

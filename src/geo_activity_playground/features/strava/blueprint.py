import pathlib
import shutil
import tempfile
import urllib.parse
import zipfile

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ...core.config import ConfigAccessor
from ...core.paths import strava_api_dir
from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes


class StravaLoginHelper:
    def __init__(self, config_accessor: ConfigAccessor) -> None:
        self._config_accessor = config_accessor

    def render_strava(self) -> dict:
        return {
            "strava_client_id": self._config_accessor.strava().strava_client_id,
            "strava_client_secret": self._config_accessor.strava().strava_client_secret,
            "strava_client_code": self._config_accessor.strava().strava_client_code,
        }

    def save_strava(self, client_id: str, client_secret: str) -> str:
        self._strava_client_id = client_id
        self._strava_client_secret = client_secret

        payload = {
            "client_id": client_id,
            "redirect_uri": url_for(".strava_callback", _external=True),
            "response_type": "code",
            "scope": "activity:read_all",
        }

        arg_string = "&".join(
            f"{key}={urllib.parse.quote(value)}" for key, value in payload.items()
        )
        return f"https://www.strava.com/oauth/authorize?{arg_string}"

    def save_strava_code(self, code: str) -> None:
        self._config_accessor.strava().strava_client_id = int(self._strava_client_id)
        self._config_accessor.strava().strava_client_secret = self._strava_client_secret
        self._config_accessor.strava().strava_client_code = code
        self._config_accessor.save()
        flash("Connected to Strava API", category="success")

    def disconnect_strava(self) -> None:
        self._config_accessor.strava().strava_client_code = None
        self._config_accessor.save()
        (strava_api_dir() / "strava_tokens.json").unlink(missing_ok=True)
        flash(_("Disconnected from Strava API"), category="success")


def _replace_strava_checkout_from_archive(zip_stream) -> None:
    target_dir = pathlib.Path("Strava Export")
    with tempfile.TemporaryDirectory(prefix="strava-upload-") as temp_dir_str:
        temp_dir = pathlib.Path(temp_dir_str)
        with zipfile.ZipFile(zip_stream) as archive:
            for zip_entry in archive.infolist():
                _extract_zip_entry(archive, zip_entry, temp_dir)

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        for path in temp_dir.iterdir():
            shutil.move(str(path), target_dir / path.name)


def _extract_zip_entry(
    archive: zipfile.ZipFile, zip_entry: zipfile.ZipInfo, destination_dir: pathlib.Path
) -> None:
    raw_name = zip_entry.filename.replace("\\", "/")
    member_path = pathlib.PurePosixPath(raw_name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError("ZIP archive contains invalid paths.")
    if not member_path.parts:
        return

    target_path = destination_dir.joinpath(*member_path.parts)
    if zip_entry.is_dir():
        target_path.mkdir(parents=True, exist_ok=True)
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(zip_entry) as source_file, open(target_path, "wb") as target_file:
        shutil.copyfileobj(source_file, target_file)


def register_strava_settings(
    blueprint: Blueprint,
    authenticator: Authenticator,
    config_accessor: ConfigAccessor,
    flasher: Flasher,
) -> None:
    """Register the Strava settings page with API connection and archive upload."""
    strava_login_helper = StravaLoginHelper(config_accessor)

    @blueprint.route("/strava", methods=["GET", "POST"])
    @needs_authentication(authenticator)
    def strava():
        if request.method == "POST":
            strava_client_id = request.form["strava_client_id"]
            strava_client_secret = request.form["strava_client_secret"]
            url = strava_login_helper.save_strava(
                strava_client_id, strava_client_secret
            )
            return redirect(url)
        return render_template(
            "settings/strava.html.j2", **strava_login_helper.render_strava()
        )

    @blueprint.route("/strava-callback")
    @needs_authentication(authenticator)
    def strava_callback():
        code = request.args.get("code", type=str)
        assert code
        strava_login_helper.save_strava_code(code)
        return redirect(url_for(".strava"))

    @blueprint.route("/strava-disconnect", methods=["POST"])
    @needs_authentication(authenticator)
    def strava_disconnect():
        strava_login_helper.disconnect_strava()
        return redirect(url_for(".strava"))

    @blueprint.route("/strava-upload", methods=["POST"])
    @needs_authentication(authenticator)
    def strava_upload():
        uploaded_archive = request.files.get("strava_checkout_zip")
        if uploaded_archive is None or uploaded_archive.filename in (None, ""):
            flasher.flash_message(
                _("Please choose a Strava ZIP archive."), FlashTypes.WARNING
            )
            return redirect(url_for(".strava"))
        if not uploaded_archive.filename.lower().endswith(".zip"):
            flasher.flash_message(
                _("Only ZIP archives are supported for Strava checkout upload."),
                FlashTypes.DANGER,
            )
            return redirect(url_for(".strava"))

        try:
            _replace_strava_checkout_from_archive(uploaded_archive.stream)
        except zipfile.BadZipFile:
            flasher.flash_message(
                _("The uploaded file is not a valid ZIP archive."), FlashTypes.DANGER
            )
            return redirect(url_for(".strava"))
        except ValueError as error:
            flasher.flash_message(str(error), FlashTypes.DANGER)
            return redirect(url_for(".strava"))

        flasher.flash_message(
            _("Uploaded Strava archive and replaced existing checkout."),
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".strava"))

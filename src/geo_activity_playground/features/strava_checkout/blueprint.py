import pathlib
import shutil
import tempfile
import zipfile

from flask import Blueprint, redirect, request, url_for

from ...webui.authenticator import Authenticator, needs_authentication
from ...webui.flasher import Flasher, FlashTypes


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


def register_strava_checkout_settings(
    blueprint: Blueprint, authenticator: Authenticator, flasher: Flasher
) -> None:
    """Register the Strava checkout archive upload route onto the settings blueprint."""

    @blueprint.route("/strava-upload", methods=["POST"])
    @needs_authentication(authenticator)
    def strava_upload():
        uploaded_archive = request.files.get("strava_checkout_zip")
        if uploaded_archive is None or uploaded_archive.filename in (None, ""):
            flasher.flash_message(
                "Please choose a Strava ZIP archive.", FlashTypes.WARNING
            )
            return redirect(url_for(".strava"))
        if not uploaded_archive.filename.lower().endswith(".zip"):
            flasher.flash_message(
                "Only ZIP archives are supported for Strava checkout upload.",
                FlashTypes.DANGER,
            )
            return redirect(url_for(".strava"))

        try:
            _replace_strava_checkout_from_archive(uploaded_archive.stream)
        except zipfile.BadZipFile:
            flasher.flash_message(
                "The uploaded file is not a valid ZIP archive.", FlashTypes.DANGER
            )
            return redirect(url_for(".strava"))
        except ValueError as error:
            flasher.flash_message(str(error), FlashTypes.DANGER)
            return redirect(url_for(".strava"))

        flasher.flash_message(
            "Uploaded Strava archive and replaced existing checkout.",
            FlashTypes.SUCCESS,
        )
        return redirect(url_for(".strava"))

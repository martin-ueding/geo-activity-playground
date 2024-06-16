import pathlib

from flask import flash
from flask import redirect
from flask import request
from flask import url_for
from werkzeug.utils import secure_filename


class UploadController:
    def render_form(self) -> dict:
        pass

    def receive(self) -> None:
        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["file"]
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(pathlib.Path("Activities") / filename)
            return redirect("/")

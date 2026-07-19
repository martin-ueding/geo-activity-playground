import functools
import logging
import pathlib
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


@functools.cache
def mkgmap_available() -> bool:
    return shutil.which("mkgmap") is not None


def build_garmin_img(osm_xml: str, name: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        osm_path = tmp_path / "tiles.osm"
        osm_path.write_text(osm_xml, encoding="utf-8")
        try:
            subprocess.run(
                [
                    "mkgmap",
                    "--gmapsupp",
                    "--transparent",
                    f"--description={name}",
                    str(osm_path),
                ],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as error:
            logger.error("mkgmap failed: %s", error.stderr.decode(errors="replace"))
            raise RuntimeError("mkgmap failed to build the Garmin map.") from error
        img_path = tmp_path / "gmapsupp.img"
        if not img_path.exists():
            raise RuntimeError("mkgmap did not produce a gmapsupp.img file.")
        return img_path.read_bytes()

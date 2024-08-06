import contextlib
import pathlib
import shutil
import subprocess


@contextlib.contextmanager
def webserver(basedir: pathlib.Path):
    command = [
        "geo-activity-playground",
        "--basedir",
        str(basedir),
        "serve",
        "--port",
        "5005",
    ]
    print(command)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
    )
    try:
        for line in process.stderr:
            print(f"[Webserver]: {line}", end="")
            if "Press CTRL+C to quit" in line:
                yield
                process.terminate()
    finally:
        process.terminate()


def copy_testdata_to_basedir(test_case: str, basedir: pathlib.Path) -> None:
    test_case_dir = pathlib.Path(__file__).parent.parent / "testdata" / test_case
    shutil.copytree(test_case_dir, basedir, dirs_exist_ok=True)

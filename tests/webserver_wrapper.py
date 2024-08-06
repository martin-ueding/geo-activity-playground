import contextlib
import pathlib
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
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for line in process.stderr:
            if b"Press CTRL+C to quit" in line:
                yield
                process.terminate()
    finally:
        process.terminate()

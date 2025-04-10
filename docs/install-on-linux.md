# Install on Linux

In this how-to guide you will install the latest stable version of this project on Linux.

The best way to install this project is using `pipx` as it decouples each program from the other ones. First ensure that you have it installed by running the command applicable to your Linux distribution:

| Distribution | Command |
| --- | --- |
| Ubuntu, Debian | `sudo apt install pipx` |
| Fedora, RedHat | `sudo dnf install pipx` |
| Arch, Manjaro | `sudo pacman -Syu python-pipx` |

Then, using `pipx`, you install the latest version using this command:

```bash
pipx install geo-activity-playground
```

## Testing whether it works

Next you can try to start the program to see whether the installation has worked correctly by just entering the following into the terminal:

```bash
geo-activity-playground --help
```

Does this work? Good! Then move on to [create a base directory](create-a-base-directory.md).

If you get an error that reads like “command not found”, then you need to [add local bin to PATH](add-local-bin-to-path.md).

## Installing updates

At some later point you likely want to upgrade to the latest version. For this use the following command:

```bash
pipx upgrade --pip-args "--upgrade-strategy eager" geo-activity-playground
```
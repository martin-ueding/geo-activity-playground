# Install on Linux

In this how-to guide you will install the latest stable version of this project on Linux.

The best way to install this project is using `uv tool` as it installs command-line tools into isolated environments. First ensure that you have `uv` installed by running the command applicable to your Linux distribution:

| Distribution | Command |
| --- | --- |
| Ubuntu, Debian | Use the official installer (shown below) |
| Fedora, RedHat | `sudo dnf install uv` |
| Arch, Manjaro | `sudo pacman -Syu uv` |

In distro repositories, the package name is generally `uv`. On Ubuntu and Debian, availability in official repos depends on the release, so the official installer is the most reliable option.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installing `uv`, ensure its tool binary directory is on your `PATH`:

```bash
uv tool update-shell
```

Then, using `uv tool`, install the latest version with this command:

```bash
uv tool install geo-activity-playground
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
uv tool upgrade geo-activity-playground
```
# Installing Stable On Linux

In this how-to guide I will show you how you can install the latest stable version of this project on Linux.

## PIPX method

The ideal way to install this project, is using `pipx`. First ensure that you have it installed:

| Distribution | Command |
| --- | --- |
| Ubuntu, Debian | `sudo apt install pipx` |
| Fedora, RedHat | `sudo dnf install pipx` |
| Arch, Manjaro | `sudo pacman -Syu python-pipx` |

Using PIPX, you can then install the latest version using this command:

```bash
pipx install geo-activity-playground
```

That should be it. You might need to ensure that the `$PATH` is correct. For that see the section below.

## PIP method

If you don't want to use PIPX, you can also use regular PIP. First install PIP:

| Distribution | Command |
| --- | --- |
| Ubuntu, Debian | `sudo apt install python3-pip` |
| Fedora, RedHat | `sudo dnf install python3-pip` |
| Arch, Manjaro | `sudo dnf install python-pip` |

Then install the package into your user directory.

```bash
pip install --user geo-activity-playground
```

That should be it. You might need to ensure that the `$PATH` is correct. For that see the section below.

## Ensure that the PATH is correct

Next you can try to start the program by just entering the following into the terminal:

```bash
geo-activity-playground --help
```

If you get a help message, everything is fine. If you get an error about _command not found_, we need to adjust your PATH. Execute the following in your command line:

```bash
xdg-open ~/.profile
```

This brings up an editor with your shell profile. Add a line containing the following at the end of the file:

```bash
PATH=$PATH:$HOME/.local/bin
```

This adds the path to your shell environment. This becomes active after you log in again. In order to apply it also to your current shell session, execute `export PATH=$PATH:$HOME/.local/bin` in the terminal window. Try the first command in this section again, you should see the help message now.

## Upgrading to the latest version

At some later point you likely want to upgrade to the latest version. For this use this command if you used PIPX:

```bash
pipx upgrade geo-activity-playground
```

If you used PIP, use this:

```bash
pip install --user --upgrade geo-activity-playground
```
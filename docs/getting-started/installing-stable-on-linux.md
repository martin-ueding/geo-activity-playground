# Installing Stable On Linux

In this how-to guide I will show you how you can install the latest stable version of this project on Linux.

Using PIP, you can install the latest version using this command:

```bash
pip install --user geo-activity-playground
```

If you get an error about the command `pip` not found, you will need to install that first. On Ubuntu or Debian use `sudo apt install python3-pip`, on Fedora or RedHat use `sudo dnf install python3-pip`. After you have installed PIP, repeat the above command.

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

At some later point you likely want to upgrade to the latest version. For this use this command:

```python
pip install --user --upgrade geo-activity-playground
```
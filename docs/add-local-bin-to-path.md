# Add local bin to PATH

If you get a “command not found” error when starting the program after the installation, you will learn how to fix it in this how-to.

On Linux systems there is a variable called `PATH` that contains the directories where programs are looked up at. The recommended installation method via `pipx` installs Geo Activity Playground into your local user directory where it will not cause trouble with other programs. Many Linux distributions are configured such that programs in user directories are ignored as a safety measure.

Open a terminal and execute the following command line to bring up a text editor to edit your shell profile:

```bash
xdg-open ~/.profile
```

Add a line containing the following at the end of the file:

```bash
PATH=$PATH:$HOME/.local/bin
```

This file will automatically become active after your next login. In order to activate it right now, execute the following:

```bash
source ~/.profile
```

The next step is to [create a base directory](create-a-base-directory.md).
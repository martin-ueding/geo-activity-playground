# Install on macOS

In this how-to guide you will install the latest stable version of this project on macOS.

I don't have a Mac myself, hence I cannot test whether this guide works. Please be so kind and give feedback if it doesn't work.

## Installing uv

As a next step, install [uv](https://docs.astral.sh/uv/getting-started/installation/). If you prefer Homebrew, you can use `brew install uv`. Otherwise, use the official installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool update-shell
```

`uv tool update-shell` ensures the user-local executable directory (usually `~/.local/bin`) is available on your `PATH`.

## Installation via uv tool

Now you have `uv` available and can install the project with this:

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
# Install on macOS

In this how-to guide you will install the latest stable version of this project on macOS.

I don't have a Mac myself, hence I cannot test whether this guide works. Please be so kind and give feedback if it doesn't work.

## Installing Homebrew

As a first step, install [Homebrew](https://brew.sh/) if you haven't done so already. For this, follow the instruction on their website. At the time of writing they suggest to open the _Terminal_ application and pasting in the following:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

## Installing pipx

Then as a next step, [install pipx](https://pipx.pypa.io/stable/installation/#on-macos). This makes use of Homebrew. At the time of writing you need to execute these commands in the terminal:

```bash
brew install pipx
pipx ensurepath
```

## Installation via pipx

Now you have `pipx` available and can install the project with this:

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
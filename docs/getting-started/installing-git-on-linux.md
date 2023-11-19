# Installing Git Version On Linux

As this project is still in development, you might want to have a peek into the development version. This is more advanced than using the stable versions, but not impossibly hard.

First you need to clone the git repository from GitHub using the following command:

```bash
git clone https://github.com/martin-ueding/geo-activity-playground.git
```

That will create a directory `geo-activity-playground` in your current working directory.

Then change into that directory:

```bash
cd geo-activity-playground
```

Next we will use [Poetry](https://python-poetry.org/) to install the dependencies of the project. First you need to make sure that you have Poetry available. On Ubuntu/Debian run `sudo apt install python3-poetry`, on Fedora/RedHat run `sudo dnf install poetry` to install it.

Then we can create the _virtual environment_:

```bash
poetry install
```

And next we can run the program:

```bash
poetry run geo-activity-playground --basedir path/to/your/playground --help
```

Replace the `--help` with the subcommands described in the help message or the other parts described this documentation.

You will need the `--basedir` option because you run the program from the source directory and not from your playground directory. If you install the stable version via PIP as described in the other page, you will not need this option.

# Updating to the latest version

Over time I will add more _commits_ to the source control system. In order to update your _clone_ to the latest version, execute the following:

```bash
git pull
```

This will download the missing changesets and apply them to your downloaded version. After that is done, you need to update your virtual environment with this:

```bash
poetry install
```

And then you can continue using it as before.
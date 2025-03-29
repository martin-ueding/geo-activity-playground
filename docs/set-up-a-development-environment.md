# Set up a development environment

In this how-to you will find the necessary steps to set up a development environment to run the latest development version and contribute code and documentation changes.

The following assumptions are made:

- You have some basic knowledge about the Git version control system.
- You have a programmer's code editor or IDE like [VS Code](https://code.visualstudio.com/) or [PyCharm](https://www.jetbrains.com/pycharm/download/?section=linux) installed.

If you want to contribute changes, you will also need these:

- You know some Python (for contributing code) or Markdown (for contributing documentation).
- You have a [GitHub](https://github.com/) account and have authentication via SSH set up or will use HTTPS.
- You know how to create a fork and a pull request.

## Obtain the Git repository

First you need to obtain the Git repository from GitHub. If you have a GitHub account and have set up your SSH key, then use SSH to clone:

```bash
git clone git@github.com:martin-ueding/geo-activity-playground.git
```

Otherwise use HTTPS:

```bash
git clone https://github.com/martin-ueding/geo-activity-playground.git
cd geo-activity-playground
```

Either way you will now have a new directory `geo-activity-playground` which contains the code.

## Set up Poetry

This project uses [Poetry](https://python-poetry.org/) for dependency management.

Unless you prefer a different method, install using `pipx` like so:

```bash
pipx install poetry
```

You might need to [add local bin to path](add-local-bin-to-path.md) if you get “command not found” errors later on.

Then you can create the development environment by letting Poetry download and install all the dependencies by executing this in the project directory:

```bash
poetry install
```

This is all what is needed regarding dependency management.

## Set up the pre-commit hook

This project also uses [pre-commit](https://pre-commit.com/) to make sure that every commit is run through some formatters and checkers. If you only want to use the development version but not contribute, you can skip this section.

Install pre-commit:

```bash
pipx install pre-commit
```

And then set it up in the project directory:

```bash
pre-commit install
```

## Open your editor or IDE

For your development environment to properly resolve all the packages, it needs to know about the virtual environment. Use Poetry to do that for you. To start VS Code (`code` on the command line), execute this from the project directory:

```bash
poetry run code .
```

## Starting the program

In order to test your changes, you can run the server from the Git repository like so:

```bash
poetry run geo-activity-playground --basedir path/to/your/basedir serve
```

## Committing changes

Do your changes like in any other Python project. Commit them. Before the commit is finalized, the pre-commit hook will run and take care of import order and code formatting. It might happen that the commit command fails. Add the new changes and then try to commit again.

Create a fork on GitHub. Push your code there. Open a pull request.
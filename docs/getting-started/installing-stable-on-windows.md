 
# Installing Stable on Windows

This how-to will show you the installation of the project on Windows. Here in the guide we use Windows 10 with the locale set to German, it should generalize to Windows 11 as well.

## Installing Python

First we need to install Python because that doesn't ship with Windows. Fortunately we can get it from the _Microsoft Store_. Open that via the start menu and you should see something like this:

![](windows-installation-01.png)

Type “Python” into the search bar at the top. In the search results you likely see different Python versions like 3.11 and 3.10. The project is compatible with 3.10 to 3.12; I'd suggest to just go with 3.12. In case that you have already installed one of the other compatible versions, you can skip this step.

Here we select Python 3.11.

![](windows-installation-02.png)

In the top right there is a blue button to install the software. Click that.

## Installing the project

After that has run through, you need to open the _Power Shell_ via the start menu. It should open a command line window like this:

![](windows-installation-03.png)

We can verify that Python is working by entering `python --version` and `pip --version`. It should give a sensible version message like this:

![](windows-installation-04.png)

Then we can ues PIP to install the project. Type the following:

    pip install -U geo-activity-playground

It should look like this:

![](windows-installation-05.png)

Then press <kbd>Enter</kbd> and it will install it, looking like this:

![](windows-installation-06.png)

That might take a while. After that has run through, it should give a success message:

![](windows-installation-10.png)

Then we're done with this window, you can close it now.

## Putting your activity files in place

Next you need to create a folder to put the files. I've placed mine just into the _Documents_ folder. In there I've created a folder named exactly “Activities”.

![](windows-installation-07.png)

Inside this folder there are my GPX/FIT/TCX/KML files as outlined in [how-to guide on using activity files](using-activity-files.md).

![](windows-installation-08.png)

You need to have at least one activity file before you can start the program.
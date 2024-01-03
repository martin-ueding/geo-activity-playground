# Using Git Version via Docker

[Docker](https://www.docker.com/) is a software that allows you to run Linux programs in a container. This how-to will show you how to build and start this project within a Docker container.

## Build the image

First you need to build the Docker image. For this download the source code and build the image using the following commands:

```bash
git clone https://github.com/martin-ueding/geo-activity-playground.git
cd geo-activity-playground
sudo docker build -t geo-activity-playground .
```

Perhaps you do not need `sudo` on your system.

## Run the image

You need to set up your files according to one of the presented methods, like activity files or the Strava API. Consult the other pages in the sidebar for the details.

Once you have your playground directory, you can launch the Docker image with the following. Be sure to replace `path/to/playground` with your path.

```bash
sudo docker run -p 5000:5000 -v path/to/playground:/data -it geo-activity-playground
```

This will start the webserver on <http://localhost:5000/>.

Note that port 5000 may not be available on macOS because of AirPlay, so you can map to another port by replacing the port specifier from above with `-p 8000:5000`. Then you can open <http://localhost:8000/> in your browser.


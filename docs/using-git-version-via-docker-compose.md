# Using Git Version via Docker Compose

[Docker](https://www.docker.com/) is a software that allows you to run Linux programs in a container.
[Docker Compose](https://docs.docker.com/compose/) is a tool for defining multi-container Docker environments in a single YAML configuration file and deploy it with a single command.

This how-to will give you an example `compose.yml` that can build the geo-activity-playground docker image from Github and start this project within a Docker container.

## Creating directory structure and compose.yml

With these steps the playground folder (which contains the activities) will be located in the docker project folder. The location can be changed in the `compose.yml`.

```bash
mkdir -p /docker/geo-activity-playground/playground/Activities
cd /docker/geo-activity-playground
nano compose.yml
```

```yml
services:
  geo-activity:
    build:
      context: https://github.com/martin-ueding/geo-activity-playground.git
      # this sets the build context to the DOCKERFILE located in the Github repository
    container_name: geo-activity-playground
    volumes:
      - /docker/geo-activity-playground/playground:/data  # optional: change left side to your desired playground directory
    ports:
      - 5000:5000 # optional: change the exposed port on the left side
    restart: unless-stopped
```

If you want to build the release version from Github instead, you can adjust the build context and add the release tag.
`context: https://github.com/martin-ueding/geo-activity-playground.git#0.29.1`

## Building image and running container

You need to set up your files according to one of the presented methods, like activity files or the Strava API. Consult the other pages in the sidebar for the details.

Once you have your playground directory, you can build the image and start the container.

```bash
docker compose build
docker compose up -d
```

This will start the webserver on <http://localhost:5000/> or at the port you chose to expose.

Note that port 5000 may not be available on macOS because of AirPlay, so you can map to another port.

## Updating the image

If using the tagged release version, update the tag to the latest one first.

```
docker compose down
docker compose build
docker compose up -d --force-recreate
```
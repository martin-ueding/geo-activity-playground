# Using Docker Compose

With Docker Compose you can download and run GAP in a long-running container, which is prepared with all needed dependencies.  
[Docker](https://www.docker.com/) is a software that allows you to run Linux programs in a container on [Linux](https://docs.docker.com/engine/install/), Mac or Windows  with [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/).  
[Docker Compose](https://docs.docker.com/compose/) is a tool for defining multi-container Docker environments in a single YAML configuration file and deploy it with a single command.

## Create a base directory

You need a [base directory](create-a-base-directory.md), where GAP stores files and activities.  
Import your activities by [Choosing an Activity Source](activity-sources.md).  

## Creating a directory for docker compose stack

The compose project needs a directory, which includes the defining `compose.yaml` file.  
The [base directory](create-a-base-directory.md) can also be in this directory e.g. `/docker/geo-activity-playground/playground`.  

```bash
mkdir -p /docker/geo-activity-playground/playground
```

`/docker/geo-activity-playground/compose.yaml`

```yaml
services:
  geo-activity-playground:
    container_name: geo-activity-playground
    image: ghcr.io/martin-ueding/geo-activity-playground:latest
    volumes:
      - /docker/geo-activity-playground/playground:/data  # if using a different base path, change the left side
    ports:
      - "127.0.0.1:5000:5000" # you can change the exposed (host) port on the left side
    restart: unless-stopped
```

## Downloading the image and running the container

```bash
cd /docker/geo-activity-playground
docker compose up -d
```

This will start the webserver on your local host: `http://127.0.0.1:5000/`.  
If you want to open GAP to your local network, use `"5000:5000"` in the `ports` section.  

Note that port 5000 may not be available on macOS because of AirPlay, so you can map to another host port e.g. `"127.0.0.1:8000:5000"` in the `ports` section.  
Then you can open `http://127.0.0.1:8000/` in your browser.  

## Stopping the container

You can temporarily stop the container (it restarts on reboot with the option `restart: unless-stopped`) with:
```bash
docker stop geo-activity-playground
```

and start again with:

```bash
docker start geo-activity-playground
```

To permanently stop the docker compose stack, use:

```bash
cd /docker/geo-activity-playground
docker compose down
```

## Updating the image and redeploy the container

```bash
cd /docker/geo-activity-playground
docker compose pull
docker compose up -d --force-recreate
```

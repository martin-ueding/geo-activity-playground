# Start with Docker Run

With Docker Run you can quickly download and start GAP in a container, which is prepared with all needed dependencies.  
[Docker](https://www.docker.com/) is a software that allows you to run Linux programs in a container on [Linux](https://docs.docker.com/engine/install/), Mac or Windows  with [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/).  

## Create a base directory

You need a [base directory](create-a-base-directory.md), where GAP stores files and activities.  
Import your activities by [Choosing an Activity Source](activity-sources.md).  

## Run the image

Once you have your playground directory, you can launch the Docker image in your terminal with the following.  
Be sure to replace `/path/to/playground` with your playground [base directory](create-a-base-directory.md).  

```bash
docker run -it \
  --name geo-activity-playground \
  -p 127.0.0.1:5000:5000 \
  -v /path/to/playground:/data \
  ghcr.io/martin-ueding/geo-activity-playground:latest
```

This will start the webserver on your local host: `http://127.0.0.1:5000/`.  
If you want ot open GAP to your local network, use `-p 5000:5000`.  

Note that port 5000 may not be available on macOS because of AirPlay, so you can map to another host port e.g. `-p 127.0.0.1:8000:5000`.  
Then you can open `http://127.0.0.1:8000/` in your browser.  

Quit with `CTRL+C` in the terminal or with the `Admin > Shutdown Server` menu in the Web UI.  

### Long running container

To keep the container running in the background, you can use `-d` option instead of `-it`.
To make it restart on the next boot, also add `--restart unless-stopped`. 
You can stop the container running in the background with `docker stop geo-activity-playground` and restart with `docker start geo-activity-playground`.  
For long running containers, concider [Using Docker Compose](using-docker-compose.md)

## Pull and update the image

Get the latest version of GAP  

```bash
docker stop geo-activity-playground
docker rm geo-activity-playground
docker pull ghcr.io/martin-ueding/geo-activity-playground:latest
```

Then you can restart GAP with the `docker run` command from above.  
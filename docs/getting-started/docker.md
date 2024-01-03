# Using Docker

Build the image:

```bash
git clone https://github.com/martin-ueding/geo-activity-playground.git
cd geo-activity-playground
docker build -t geo-activity-playground .
```

Run the image:

```bash
mkdir data
# if you are using local activies, create the folder:
mkdir data/Activities
# and/or create/edit data/config.toml
cp config.toml.example data/config.toml

docker -v -p 5000:5000 "$PWD/data":/data -it geo-activity-playground --basedir /data serve --host 0.0.0.0
```

Running on MacOS - Note that port 5000 may not be available because of AirPlay, so you can map to another port:

```bash
docker run -p 8000:5000 -v "$PWD/data:/data" gap --basedir /data serve --host 0.0.0.0
```

And open http://localhost:8000/ in your browser.



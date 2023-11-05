# Explorer Tiles

## What are explorer tiles?

Maps accessible via the web browser are usually served as little image tiles. The Open Street Map uses the _Web Mercator_ coordinate system to map from latitude and longitude to pixels on the map.

Each tile is 256 × 256 pixels in size. The zoom levels zoom in by a factor of two. Therefore all the tiles are organized in a _quad tree_. As you zoom in, each tile gets split into four tiles which can then show more detail. The following prescription maps from latitude and longitude (given in degrees) to tile indices:

```python
def compute_tile(lat: float, lon: float, zoom: int = 14) -> tuple[int, int]:
    x = np.radians(lon)
    y = np.arcsinh(np.tan(np.radians(lat)))
    x = (1 + x / np.pi) / 2
    y = (1 - y / np.pi) / 2
    n = 2**zoom
    return int(x * n), int(y * n)
```

At zoom level 14 the tiles have a side length of roughly 1.5 km where I live. These tiles are used as the basis for _explorer tiles_. The basic idea is that every tile where you have at least one point in an activity is considered an _explored tile_.

From your activities the program will extract all the tiles that you have visited. And then it does a few things with those.

## Maps with explorer tiles

The most straightforward artifact is a map with all the tiles that you have explored. This is created in the GeoJSON format as that can encode polygons. You can then take a look at these maps with programs like [GPXSee](https://www.gpxsee.org/) or online viewers like [GeoJSON.io](http://geojson.io/).

The explored tiles map looks like this for the Hunsrück area for me:

![](explorer-explored.png)

## Missing tiles

The next interesting question are the missing tiles. I often have little gaps and would like to see them easily. The program computes the boundary around the tiles that you have explored. This can be used to plan extensions of the explored area.

![](explorer-missing.png)

On Android one can use the OsmAnd app to display tracks and also try to visualize the missing tiles. Unfortunately [GeoJSON is not supported](https://osmand.net/docs/technical/osmand-file-formats/), therefore one has to play some tricks. The missing tiles are also exported as a GPX file with a track for each missing tile. This looks strange, but it is a bit helpful with OsmAnd. This is how the file looks like in GPXSee:

![](explorer-missing-gpx.png)

Transfer this GPX file to OsmAnd and you can have it display the missing tiles such that you can extend your explored area systematically.
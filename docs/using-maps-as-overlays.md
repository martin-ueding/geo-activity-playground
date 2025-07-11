# Using Maps as Overlays

You can use the explorer tile maps and the heatmap as overlays elsewhere. For that, use the following URLs:

For the base layers, you can use these URLs:

```
http://localhost:5000/tile/grayscale/{z}/{x}/{y}.png
http://localhost:5000/tile/pastel/{z}/{x}/{y}.png
http://localhost:5000/tile/color/{z}/{x}/{y}.png
http://localhost:5000/tile/inverse_grayscale/{z}/{x}/{y}.png
```

For the explorer tiles, you can use these:

```
http://localhost:5000/explorer/14/tile/{z}/{x}/{y}.png?color_strategy=colorful_cluster
http://localhost:5000/explorer/14/tile/{z}/{x}/{y}.png?color_strategy=max_cluster
http://localhost:5000/explorer/14/tile/{z}/{x}/{y}.png?color_strategy=first
http://localhost:5000/explorer/14/tile/{z}/{x}/{y}.png?color_strategy=last
http://localhost:5000/explorer/14/tile/{z}/{x}/{y}.png?color_strategy=visits

http://localhost:5000/explorer/17/tile/{z}/{x}/{y}.png?color_strategy=colorful_cluster
http://localhost:5000/explorer/17/tile/{z}/{x}/{y}.png?color_strategy=max_cluster
http://localhost:5000/explorer/17/tile/{z}/{x}/{y}.png?color_strategy=first
http://localhost:5000/explorer/17/tile/{z}/{x}/{y}.png?color_strategy=last
http://localhost:5000/explorer/17/tile/{z}/{x}/{y}.png?color_strategy=visits
```

And for the heatmap, you can use these:

```
http://localhost:5000/heatmap/tile/{z}/{x}/{y}.png
```

## Adding them to Bike Router

Go to [Bike Router](https://bikerouter.de) and then you can add these as overlay layers. I show it here with the explorer tiles on zoom 17 with the "colorful cluster" strategy:

![](images/bikerouter-overlay-2.png)

![](images/bikerouter-overlay-3.png)

![](images/bikerouter-overlay-4.png)

![](images/bikerouter-overlay-5.png)

And now you can plan routes with your explorer tiles overlaid. Or add the heatmap. Or both.
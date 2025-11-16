function add_layers_to_map(map, zoom, map_tile_attribution, base = 'Grayscale', overlay = "Colorful Cluster") {
    let base_maps = {
        "Grayscale": L.tileLayer("/tile/grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Pastel": L.tileLayer("/tile/pastel/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Color": L.tileLayer("/tile/color/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Inverse Grayscale": L.tileLayer("/tile/inverse_grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Blank": L.tileLayer("/tile/blank/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
    }

    let overlay_maps = {
        "Colorful Cluster": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=colorful_cluster`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Max Cluster": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=max_cluster`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "First Visit": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=first`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Last Visit": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=last`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Number of Visits": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=visits`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Visited": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=visited`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Missing": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=missing`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        }),
        "Heatmap": L.tileLayer("/heatmap/tile/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution
        })
    }

    if (typeof square_size !== 'undefined') {
        overlay_maps["Square Planner"] = L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=square_planner&x=${square_x}&y=${square_y}&size=${square_size}`, {
            maxZoom: 19,
            attribution: map_tile_attribution
        });
        overlay = "Square Planner";
    }

    base_maps[base].addTo(map)
    overlay_maps[overlay].addTo(map)

    var layerControl = L.control.layers(base_maps, overlay_maps).addTo(map);
}
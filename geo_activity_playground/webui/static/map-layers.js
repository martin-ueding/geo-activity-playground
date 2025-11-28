function add_layers_to_map(map, zoom, map_tile_attribution, base = 'Grayscale', overlay = "Colorful Cluster") {
    // Get map container ID for localStorage key
    const mapId = map.getContainer().id;
    const storageKey = `map-layers-${mapId}`;
    
    // Load saved preferences if available
    let saved = {};
    try {
        saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
    } catch (e) {
        console.warn('Failed to load saved map layers:', e);
    }

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

    // Use saved preferences if valid, otherwise fall back to defaults
    const selectedBase = (saved.base && base_maps[saved.base]) ? saved.base : base;
    const selectedOverlay = (saved.overlay && overlay_maps[saved.overlay]) ? saved.overlay : overlay;

    base_maps[selectedBase].addTo(map)
    overlay_maps[selectedOverlay].addTo(map)

    var layerControl = L.control.layers(base_maps, overlay_maps).addTo(map);

    // Save layer selections to localStorage
    map.on('baselayerchange', (e) => {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            current.base = e.name;
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save base layer preference:', err);
        }
    });

    map.on('overlayadd', (e) => {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            current.overlay = e.name;
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save overlay preference:', err);
        }
    });
}
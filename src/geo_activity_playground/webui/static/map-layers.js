/**
 * Adds base and overlay tile layers to a Leaflet map with layer control.
 * 
 * @param {L.Map} map - The Leaflet map instance
 * @param {Object} config - Configuration object
 * @param {number} config.zoom - Primary explorer tile zoom level (drives the default overlay selection)
 * @param {number[]} [config.zoomLevels] - All enabled explorer zoom levels to offer in the layer control (defaults to [zoom])
 * @param {string} config.attribution - Map tile attribution text
 * @param {string} [config.baseLayer='Grayscale'] - Default base layer name
 * @param {string|null} [config.overlay='Colorful Cluster'] - Default overlay strategy, or null for no overlay
 * @param {Object} [config.squarePlanner] - Square planner config (optional)
 * @param {number} config.squarePlanner.x - Square X coordinate
 * @param {number} config.squarePlanner.y - Square Y coordinate
 * @param {number} config.squarePlanner.size - Square size
 * @param {string} [config.heatmapExtraArgs] - Extra URL args for heatmap tiles
 * @param {number} [config.historyEventIndex] - Optional cluster-history cutoff index
 */
export function add_layers_to_map(map, config) {
    const {
        zoom,
        zoomLevels = [zoom],
        attribution,
        baseLayer = 'Grayscale',
        overlay = 'Colorful Cluster',
        squarePlanner = null,
        heatmapExtraArgs = null,
        historyEventIndex = null
    } = config;

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

    const base_maps = {
        "Grayscale": L.tileLayer("/tile/grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Pastel": L.tileLayer("/tile/pastel/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Color": L.tileLayer("/tile/color/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Inverse Grayscale": L.tileLayer("/tile/inverse_grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Blank": L.tileLayer("/tile/blank/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
    };

    // Build heatmap URL with optional extra args
    let heatmap_url = "/heatmap/tile/{z}/{x}/{y}.png";
    if (heatmapExtraArgs) {
        heatmap_url += `?${heatmapExtraArgs}`;
    }

    const mapterhornPaneName = "mapterhorn-hillshade";
    if (!map.getPane(mapterhornPaneName)) {
        const pane = map.createPane(mapterhornPaneName);
        pane.style.zIndex = "380";
        pane.style.mixBlendMode = "multiply";
        pane.style.pointerEvents = "none";
    }

    if (!(L.gridLayer && L.gridLayer.relief)) {
        console.error("leaflet-relief is required for Mapterhorn hillshade but is not available.");
    }

    const historyParam = Number.isInteger(historyEventIndex)
        ? `&event_index=${historyEventIndex}`
        : '';

    // Explorer overlay strategies. Each becomes one entry per enabled zoom level.
    const explorerStrategies = [
        { name: "Colorful Cluster", strategy: "colorful_cluster", history: true },
        { name: "Max Cluster", strategy: "max_cluster", history: true },
        { name: "First Visit", strategy: "first" },
        { name: "Last Visit", strategy: "last" },
        { name: "Number of Visits", strategy: "visits" },
        { name: "Visited", strategy: "visited" },
        { name: "Missing", strategy: "missing" },
    ];
    const explorerNames = new Set(explorerStrategies.map(s => s.name));

    // Prefix with "Explorer {zoom}" when there is more than one zoom level, so that
    // the entries cluster by zoom level in the layer control.
    const labelFor = (name, z) => zoomLevels.length > 1 ? `Explorer ${z} ${name}` : name;

    const overlay_maps = {
        "Mapterhorn Hillshade": (L.gridLayer && L.gridLayer.relief)
            ? L.gridLayer.relief({
                mode: "hillshade",
                tileSize: 256,
                elevationUrl: L.GridLayer.Relief.elevationUrls.mapterhorn,
                elevationExtractor: L.GridLayer.Relief.elevationExtractors.mapterhorn,
                attribution: L.GridLayer.Relief.elevationAttributions.mapterhorn,
                hillshadeColorFunction: (intensity) => {
                    const gray = Math.round(255 * intensity);
                    return [gray, gray, gray];
                },
                opacity: 0.5,
                maxZoom: 17,
                pane: mapterhornPaneName
            })
            : L.layerGroup(),
    };

    for (const z of zoomLevels) {
        for (const { name, strategy, history } of explorerStrategies) {
            const extra = history ? historyParam : '';
            overlay_maps[labelFor(name, z)] = L.tileLayer(
                `/explorer/${z}/tile/{z}/{x}/{y}.png?color_strategy=${strategy}${extra}`,
                { maxZoom: 19, attribution }
            );
        }
    }

    overlay_maps["Heatmap"] = L.tileLayer(heatmap_url, {
        maxZoom: 19,
        attribution
    });

    // Resolve the default overlay strategy to a concrete entry at the primary zoom.
    let selectedOverlay = explorerNames.has(overlay) ? labelFor(overlay, zoom) : overlay;

    if (squarePlanner) {
        const { x, y, size } = squarePlanner;
        overlay_maps["Square Planner"] = L.tileLayer(
            `/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=square_planner&x=${x}&y=${y}&size=${size}`,
            { maxZoom: 19, attribution }
        );
        selectedOverlay = "Square Planner";
    }

    // Use saved preferences if valid, otherwise fall back to defaults
    const selectedBase = (saved.base && base_maps[saved.base]) ? saved.base : baseLayer;

    // Explorer overlays are remembered by strategy, not by zoom level, so that
    // navigating between explorer pages always shows the strategy at the page's own
    // zoom rather than whichever zoom happened to be active when it was saved.
    const overlayBaseName = (label) => {
        const m = label.match(/^Explorer \d+ (.*)$/);
        return m ? m[1] : label;
    };
    const resolveSavedOverlay = (base) => explorerNames.has(base) ? labelFor(base, zoom) : base;

    // In square planner mode the active overlay must be deterministic and tied to URL
    // parameters; saved overlays can otherwise hide the planner layer.
    const defaultOverlays = selectedOverlay ? [selectedOverlay] : [];
    let selectedOverlays;
    if (squarePlanner) {
        selectedOverlays = [selectedOverlay];
    } else if (saved.overlays && Array.isArray(saved.overlays)) {
        const savedOverlays = saved.overlays
            .map(resolveSavedOverlay)
            .filter(name => overlay_maps[name]);
        selectedOverlays = savedOverlays.length > 0 ? savedOverlays : defaultOverlays;
    } else {
        // Fall back to default (single overlay as array, or none)
        selectedOverlays = defaultOverlays;
    }

    base_maps[selectedBase].addTo(map);
    selectedOverlays.forEach(name => overlay_maps[name].addTo(map));

    L.control.layers(base_maps, overlay_maps).addTo(map);

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

    // Helper to save all currently active overlays
    function saveOverlays() {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            const active = Object.keys(overlay_maps)
                .filter(name => map.hasLayer(overlay_maps[name]))
                .map(overlayBaseName);
            current.overlays = [...new Set(active)];
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save overlay preference:', err);
        }
    }

    map.on('overlayadd', saveOverlays);
    map.on('overlayremove', saveOverlays);
}

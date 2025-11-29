/**
 * Adds base and overlay tile layers to a Leaflet map with layer control.
 * 
 * @param {L.Map} map - The Leaflet map instance
 * @param {Object} config - Configuration object
 * @param {number} config.zoom - Explorer tile zoom level
 * @param {string} config.attribution - Map tile attribution text
 * @param {string} [config.baseLayer='Grayscale'] - Default base layer name
 * @param {string} [config.overlay='Colorful Cluster'] - Default overlay name
 * @param {Object} [config.squarePlanner] - Square planner config (optional)
 * @param {number} config.squarePlanner.x - Square X coordinate
 * @param {number} config.squarePlanner.y - Square Y coordinate
 * @param {number} config.squarePlanner.size - Square size
 * @param {string} [config.heatmapExtraArgs] - Extra URL args for heatmap tiles
 */
export function add_layers_to_map(map, config) {
    const {
        zoom,
        attribution,
        baseLayer = 'Grayscale',
        overlay = 'Colorful Cluster',
        squarePlanner = null,
        heatmapExtraArgs = null
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

    const overlay_maps = {
        "Colorful Cluster": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=colorful_cluster`, {
            maxZoom: 19,
            attribution
        }),
        "Max Cluster": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=max_cluster`, {
            maxZoom: 19,
            attribution
        }),
        "First Visit": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=first`, {
            maxZoom: 19,
            attribution
        }),
        "Last Visit": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=last`, {
            maxZoom: 19,
            attribution
        }),
        "Number of Visits": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=visits`, {
            maxZoom: 19,
            attribution
        }),
        "Visited": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=visited`, {
            maxZoom: 19,
            attribution
        }),
        "Missing": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=missing`, {
            maxZoom: 19,
            attribution
        }),
        "Heatmap": L.tileLayer(heatmap_url, {
            maxZoom: 19,
            attribution
        })
    };

    // Determine which overlay to select by default
    let selectedOverlay = overlay;
    
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
    
    // Overlays: saved.overlays is an array, filter to only valid ones
    let selectedOverlays;
    if (saved.overlays && Array.isArray(saved.overlays)) {
        selectedOverlays = saved.overlays.filter(name => overlay_maps[name]);
    } else {
        // Fall back to default (single overlay as array)
        selectedOverlays = [selectedOverlay];
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
            current.overlays = Object.keys(overlay_maps).filter(name => map.hasLayer(overlay_maps[name]));
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save overlay preference:', err);
        }
    }

    map.on('overlayadd', saveOverlays);
    map.on('overlayremove', saveOverlays);
}

import { add_layers_to_map } from '/static/map-layers.js';

/**
 * Initialize the explorer map.
 * 
 * @param {Object} config - Configuration object
 * @param {string} config.elementId - ID of the map container element
 * @param {number} config.centerLatitude - Initial center latitude
 * @param {number} config.centerLongitude - Initial center longitude
 * @param {number} config.zoom - Explorer tile zoom level
 * @param {string} config.attribution - Map tile attribution
 * @param {Object} [config.bbox] - Initial bounding box as GeoJSON (optional)
 * @param {Object} [config.squarePlanner] - Square planner config (optional)
 */
export function initExplorerMap(config) {
    const {
        elementId = 'explorer-map',
        centerLatitude,
        centerLongitude,
        zoom,
        attribution,
        bbox = null,
        squarePlanner = null
    } = config;

    const map = L.map(elementId, {
        fullscreenControl: true,
        center: [centerLatitude, centerLongitude],
        zoom: 12
    });

    add_layers_to_map(map, {
        zoom,
        attribution,
        squarePlanner
    });

    // Fit to bounding box if provided
    if (bbox) {
        map.fitBounds(L.geoJSON(bbox).getBounds(), { padding: [30, 30] });
    }

    // Click handler to show tile info popup
    map.on('click', e => {
        fetch(`/explorer/${zoom}/info/${e.latlng.lat}/${e.latlng.lng}`)
            .then(response => response.text())
            .then(text => {
                L.popup()
                    .setLatLng(e.latlng)
                    .setContent(text)
                    .openOn(map);
            });
    });

    // Set up event listeners for elements with data attributes
    setupCenterOnButtons(map);
    setupDownloadLinks(map, zoom);

    return map;
}

/**
 * Set up click handlers for buttons with data-bbox attribute.
 * These buttons center the map on a specific bounding box.
 */
function setupCenterOnButtons(map) {
    const buttons = document.querySelectorAll('[data-center-bbox]');
    let ignoreNextMove = false;

    buttons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons
            buttons.forEach(b => b.classList.remove('active'));
            // Add active class to clicked button
            button.classList.add('active');
            // Ignore the map move triggered by fitBounds
            ignoreNextMove = true;

            const bbox = JSON.parse(button.dataset.centerBbox);
            map.fitBounds(L.geoJSON(bbox).getBounds(), { padding: [30, 30] });
        });
    });

    // Remove active state when user manually pans or zooms
    map.on('movestart', () => {
        if (ignoreNextMove) {
            ignoreNextMove = false;
            return;
        }
        buttons.forEach(b => b.classList.remove('active'));
    });
}

/**
 * Set up click handlers for links with data-download-suffix attribute.
 * These links download tiles in the visible area.
 */
function setupDownloadLinks(map, zoom) {
    document.querySelectorAll('[data-download-suffix]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const suffix = link.dataset.downloadSuffix;
            const bounds = map.getBounds();
            window.location.href = `/explorer/${zoom}/${bounds.getNorth()}/${bounds.getEast()}/${bounds.getSouth()}/${bounds.getWest()}/${suffix}`;
        });
    });
}

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

    initClusterHistoryLayer(map, zoom);

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

function initClusterHistoryLayer(map, zoom) {
    const loadButton = document.getElementById('load-cluster-history');
    const controls = document.getElementById('cluster-history-controls');
    const slider = document.getElementById('cluster-history-slider');
    const label = document.getElementById('cluster-history-value');
    const maxLabel = document.getElementById('cluster-history-max');
    const status = document.getElementById('cluster-history-status');
    if (!loadButton || !controls || !slider || !label || !maxLabel || !status) {
        return;
    }

    const clusterLayer = L.geoJSON(null, {
        style: {
            color: '#0057e7',
            weight: 2,
            fillOpacity: 0.15
        }
    });

    const loadSnapshot = async (eventIndex) => {
        const response = await fetch(
            `/explorer/${zoom}/cluster-history/snapshot.geojson?event_index=${eventIndex}`
        );
        if (!response.ok) {
            throw new Error(`Loading snapshot failed with status ${response.status}`);
        }
        const data = await response.json();
        clusterLayer.clearLayers();
        clusterLayer.addData(data);
    };

    slider.disabled = true;

    loadButton.addEventListener('click', async () => {
        loadButton.disabled = true;
        status.textContent = 'Loading cluster history...';

        try {
            const metadataResponse = await fetch(
                `/explorer/${zoom}/cluster-history/metadata.json`
            );
            if (!metadataResponse.ok) {
                throw new Error(
                    `Loading metadata failed with status ${metadataResponse.status}`
                );
            }
            const metadata = await metadataResponse.json();
            const maxEventIndex = metadata.latest_event_index ?? 0;

            if (maxEventIndex <= 0) {
                status.textContent = 'No cluster history available.';
                return;
            }

            slider.max = String(maxEventIndex);
            slider.value = String(maxEventIndex);
            label.textContent = String(maxEventIndex);
            maxLabel.textContent = String(maxEventIndex);
            slider.disabled = false;
            controls.classList.remove('d-none');

            if (!map.hasLayer(clusterLayer)) {
                clusterLayer.addTo(map);
            }
            await loadSnapshot(maxEventIndex);
            status.textContent = '';
        } catch (error) {
            console.error('Failed to load cluster history layer:', error);
            status.textContent = 'Could not load cluster history.';
            loadButton.disabled = false;
        }
    });

    slider.addEventListener('input', () => {
        const eventIndex = Number.parseInt(slider.value, 10) || 0;
        label.textContent = String(eventIndex);
        loadSnapshot(eventIndex).catch(error => {
            console.error('Failed to update cluster history layer:', error);
            status.textContent = 'Could not update cluster history.';
        });
    });
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

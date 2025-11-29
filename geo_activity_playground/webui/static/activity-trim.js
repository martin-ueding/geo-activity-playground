/**
 * Initialize the activity trim map.
 * 
 * @param {Object} config - Configuration object
 * @param {string} config.elementId - ID of the map container element
 * @param {string} config.attribution - Map tile attribution
 * @param {Object} config.geojson - GeoJSON data for the activity track
 * @param {string} config.beginInputId - ID of the begin index input field
 * @param {string} config.endInputId - ID of the end index input field
 */
export function initActivityTrimMap(config) {
    const {
        elementId = 'activity-trim-map',
        attribution,
        geojson,
        beginInputId = 'begin',
        endInputId = 'end'
    } = config;

    const map = L.map(elementId, {
        fullscreenControl: true
    });

    L.tileLayer('/tile/pastel/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution
    }).addTo(map);

    const layer = L.geoJSON(geojson, {
        pointToLayer: function (feature, latLng) {
            const p = feature.properties;

            let marker;
            if (p.markerType === "circle") {
                marker = L.circleMarker(latLng, p.markerStyle);
            } else {
                marker = L.marker(latLng);
            }

            if (p.name !== undefined) {
                const popupContent = createTrimPopup(p.name, beginInputId, endInputId);
                marker.bindPopup(popupContent);
            }

            return marker;
        }
    });

    layer.addTo(map);
    map.fitBounds(layer.getBounds());

    return map;
}

/**
 * Create popup content with buttons for setting trim points.
 * Uses event delegation via data attributes.
 */
function createTrimPopup(index, beginInputId, endInputId) {
    const container = document.createElement('div');
    
    const beginBtn = document.createElement('button');
    beginBtn.className = 'btn btn-primary';
    beginBtn.textContent = 'Use as Begin';
    beginBtn.addEventListener('click', () => {
        document.getElementById(beginInputId).value = index;
    });
    
    const endBtn = document.createElement('button');
    endBtn.className = 'btn btn-primary';
    endBtn.textContent = 'Use as End';
    endBtn.style.marginLeft = '0.5em';
    endBtn.addEventListener('click', () => {
        document.getElementById(endInputId).value = index + 1;
    });
    
    container.appendChild(beginBtn);
    container.appendChild(endBtn);
    
    return container;
}

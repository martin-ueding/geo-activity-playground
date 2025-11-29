const map = L.map('activity-trim-map', {
    fullscreenControl: true
});
L.tileLayer('/tile/pastel/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: map_tile_attribution
}).addTo(map);

function copy_to_input(value, input) {
    document.getElementById(input).value = value;
}

// Expose to window for onclick handlers in dynamically generated popups
window.copy_to_input = copy_to_input;

const layer = L.geoJSON(color_line_geojson, {
    pointToLayer: function (feature, lat_lon) {
        const p = feature.properties

        let marker = null
        if (p.markerType == "circle") {
            marker = L.circleMarker(lat_lon, p.markerStyle)
        } else {
            marker = L.marker(lat_lon)
        }

        let text = ''
        if (p.name) {
            text += `<button class="btn btn-primary" onclick="copy_to_input(${p.name}, 'begin')">Use as Begin</button>`
            text += ' '
            text += `<button class="btn btn-primary" onclick="copy_to_input(${p.name}+1, 'end')">Use as End</button>`
        }
        if (text) {
            marker = marker.bindPopup(text)
        }

        return marker
    }
})

layer.addTo(map)
map.fitBounds(layer.getBounds());
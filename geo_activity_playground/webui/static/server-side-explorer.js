let map = L.map('explorer-map', {
    fullscreenControl: true,
    center: [center_latitude, center_longitude],
    zoom: 12
});

add_layers_to_map(map, zoom, map_tile_attribution);

if (bbox) {
    map.fitBounds(L.geoJSON(bbox).getBounds(), { padding: [30, 30] })
}

function centerOn(bbox) {
    map.fitBounds(L.geoJSON(bbox).getBounds(), { padding: [30, 30] })
}

if (bbox) {
    centerOn(bbox)
}

map.on('click', e => {
    fetch(`/explorer/${zoom}/info/${e.latlng.lat}/${e.latlng.lng}`)
        .then(response => response.text())
        .then(text => {
            L.popup()
                .setLatLng(e.latlng)
                .setContent(text)
                .openOn(map);
        }
        );
});

function downloadAs(suffix) {
    bounds = map.getBounds();
    window.location.href = `/explorer/${zoom}/${bounds.getNorth()}/${bounds.getEast()}/${bounds.getSouth()}/${bounds.getWest()}/${suffix}`
}

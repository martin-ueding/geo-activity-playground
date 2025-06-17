
let tile_layer = null

function changeColor(method) {
    if (tile_layer) {
        map.removeLayer(tile_layer)
    }
    tile_layer = L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=${method}`, {
        maxZoom: 19,
        attribution: map_tile_attribution
    }).addTo(map)
}

let map = L.map('explorer-map', {
    fullscreenControl: true,
    center: [center_latitude, center_longitude],
    zoom: 12
});

changeColor('default')

if (bbox) {
    map.fitBounds(L.geoJSON(bbox).getBounds())
}

map.on('click', e => {
    fetch(`/explorer/${zoom}/info/${e.latlng.lat}/${e.latlng.lng}`)
        .then(response => response.json())
        .then(data => {
            if (!data.tile_xy) {
                return;
            }
            console.debug(data);

            let lines = [
                `<dt>Tile</dt>`,
                `<dd>${data.tile_xy}</dd>`,
                `<dt>First visit</dt>`,
                `<dd>${data.first_time}</br><a href=/activity/${data.first_activity_id}>${data.first_activity_name}</a></dd>`,
                `<dt>Last visit</dt>`,
                `<dd>${data.last_time}</br><a href=/activity/${data.last_activity_id}>${data.last_activity_name}</a></dd>`,
                `<dt>Number of visits</dt>`,
                `<dd>${data.num_visits}</dd>`,
            ]
            if (data.this_cluster_size) {
                lines.push(`<dt>This cluster size</dt><dd>${data.this_cluster_size}</dd>`)
            }

            L.popup()
                .setLatLng(e.latlng)
                .setContent('<dl>' + lines.join('') + '</dl>')
                .openOn(map);
        }
        );
});

function downloadAs(suffix) {
    bounds = map.getBounds();
    window.location.href = `/explorer/${zoom}/${bounds.getNorth()}/${bounds.getEast()}/${bounds.getSouth()}/${bounds.getWest()}/${suffix}`
}
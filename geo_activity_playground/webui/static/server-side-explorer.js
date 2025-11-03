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
                if (data.new_bookmark_url === undefined) {
                    console.error("Somehow we got a cluster that doesn't have a proper URL. This is the data that we got in response:")
                    console.error(data)
                } else {
                    lines.push(`<dt>Bookmark</dt><dd><a href="${data.new_bookmark_url}">Create cluster bookmark</a></dd>`)
                }
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

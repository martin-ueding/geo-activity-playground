let map = L.map('explorer-map', {
    fullscreenControl: true,
    center: [center_latitude, center_longitude],
    zoom: 12
});

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
    "Mising": L.tileLayer(`/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=missing`, {
        maxZoom: 19,
        attribution: map_tile_attribution
    }),
    "Heatmap": L.tileLayer("/heatmap/tile/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: map_tile_attribution
    }),
}

base_maps['Grayscale'].addTo(map)
overlay_maps["Colorful Cluster"].addTo(map)

var layerControl = L.control.layers(base_maps, overlay_maps).addTo(map);

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
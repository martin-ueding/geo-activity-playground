document.addEventListener("DOMContentLoaded", function () {
    let map = L.map("explorer-map", {
        fullscreenControl: true,
        center: [0.0, 0.0],
        zoom: 14,
    });

    let base_maps = {
        Grayscale: L.tileLayer("/tile/grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution,
        }),
        Pastel: L.tileLayer("/tile/pastel/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution,
        }),
        Color: L.tileLayer("/tile/color/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: map_tile_attribution,
        }),
        "Inverse Grayscale": L.tileLayer(
            "/tile/inverse_grayscale/{z}/{x}/{y}.png",
            {
                maxZoom: 19,
                attribution: map_tile_attribution,
            },
        ),
    };

    base_maps["Grayscale"].addTo(map);

    let layerControl = L.control.layers(base_maps).addTo(map);

    let explorer_layer_cluster_color = L.geoJSON(explorer_geojson, {
        style: function (feature) {
            return {
                color: "#4daf4a",
                fillColor: "#4daf4a",
                weight: 0.5,
            };
        },
    }).addTo(map);

    let missing_layer_cluster_color = L.geoJSON(missing_geojson, {
        style: function (feature) {
            return {
                color: "#e41a1c",
                fillColor: "#e41a1c",
                weight: 0.5,
            };
        },
    }).addTo(map);

    let explorer_square_layer = L.geoJSON(square_geojson, {
        style: function (feature) {
            return {
                color: "blue",
                fill: false,
                weight: 2,
            };
        },
    }).addTo(map);

    map.fitBounds(explorer_square_layer.getBounds());
});

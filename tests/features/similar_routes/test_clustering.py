from geo_activity_playground.features.similar_routes.backfill import (
    RouteDistanceBackfill,
)
from geo_activity_playground.features.similar_routes.clustering import (
    cluster_routes,
    find_cluster,
    load_neighbors,
)

from .test_backfill import add_activity, run_until_idle


def test_center_is_the_activity_with_most_neighbors() -> None:
    clusters = cluster_routes(
        {
            1: {2: 10.0, 3: 20.0},
            2: {1: 10.0},
            3: {1: 20.0, 4: 30.0},
            4: {3: 30.0},
        }
    )
    assert [c.center_id for c in clusters] == [1]
    assert clusters[0].distances_to_center_m == {1: 0.0, 2: 10.0, 3: 20.0}


def test_chains_are_not_merged() -> None:
    chain = {
        1: {2: 50.0},
        2: {1: 50.0, 3: 50.0},
        3: {2: 50.0, 4: 50.0},
        4: {3: 50.0, 5: 50.0},
        5: {4: 50.0},
    }
    clusters = cluster_routes(chain)
    assert [sorted(c.member_ids) for c in clusters] == [[1, 2, 3], [4, 5]]


def test_ties_prefer_smaller_distances() -> None:
    clusters = cluster_routes(
        {
            1: {2: 80.0, 3: 5.0},
            2: {1: 80.0},
            3: {1: 5.0, 4: 1.0},
            4: {3: 1.0},
        }
    )
    assert clusters[0].center_id == 3
    assert find_cluster(clusters, 2) is None


def test_clusters_from_database(app_context, road) -> None:
    ids = [
        add_activity("a", 1, road(0, 2000, 5)),
        add_activity("b", 2, road(0, 2000, 7, north_m=10)),
        add_activity("partial", 3, road(500, 1500, 7)),
        add_activity("far", 4, road(0, 2000, 5, north_m=10_000)),
    ]
    run_until_idle(RouteDistanceBackfill())

    clusters = cluster_routes(load_neighbors("p95", 50))
    assert len(clusters) == 1
    assert sorted(clusters[0].member_ids) == ids[:2]


def test_pages_render(client, app_context, road) -> None:
    a = add_activity("a", 1, road(0, 2000, 5))
    add_activity("b", 2, road(0, 2000, 7, north_m=10))
    lonely = add_activity("lonely", 3, road(0, 2000, 5, north_m=10_000))
    run_until_idle(RouteDistanceBackfill())

    assert client.get("/similar-routes/clusters").status_code == 200
    response = client.get(f"/similar-routes/cluster/{a}?quantile=p75&max_distance_m=50")
    assert response.status_code == 200
    assert b"map-cluster" in response.data
    response = client.get(f"/similar-routes/cluster/{lonely}")
    assert response.status_code == 200
    assert b"map-cluster" not in response.data

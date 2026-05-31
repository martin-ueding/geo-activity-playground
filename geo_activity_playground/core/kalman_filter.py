import numpy as np
import pandas as pd

from .coordinates import get_distance

EARTH_RADIUS = 6_371_000.0  # metres


def kalman_filter_track(
    time_series: pd.DataFrame,
    sigma_gps: float,
    sigma_process: float,
    gate_chi2: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Run a constant-velocity Kalman filter with innovation gating over a GPS track.

    State vector: [x, y, vx, vy] in a local flat-earth projection (metres, m/s).
    Measurement: GPS position [x_meas, y_meas].
    A sample is excluded when its Mahalanobis distance² exceeds gate_chi2.

    Returns (filtered_lat, filtered_lon, excluded_mask).
    """
    lat = time_series["latitude"].values.astype(float)
    lon = time_series["longitude"].values.astype(float)
    times = time_series["time"].values
    n = len(lat)

    # Local tangential projection centred on track mean
    lat_ref = np.nanmean(lat)
    lon_ref = np.nanmean(lon)
    deg_to_m = np.radians(1.0) * EARTH_RADIUS
    meas_x = (lon - lon_ref) * deg_to_m * np.cos(np.radians(lat_ref))
    meas_y = (lat - lat_ref) * deg_to_m

    H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    R = np.eye(2) * sigma_gps**2

    state = np.array([meas_x[0], meas_y[0], 0.0, 0.0])
    # Start with large positional uncertainty so the first real measurement dominates
    P = np.diag([sigma_gps**2, sigma_gps**2, 10.0**2, 10.0**2])

    filtered_x = np.empty(n)
    filtered_y = np.empty(n)
    excluded = np.zeros(n, dtype=bool)
    filtered_x[0] = state[0]
    filtered_y[0] = state[1]

    # Detect segment breaks via segment_id column or large time gaps
    has_segments = "segment_id" in time_series.columns

    for i in range(1, n):
        # Reset at segment boundary so a pause doesn't propagate stale velocity
        if has_segments:
            new_segment = (
                time_series["segment_id"].iloc[i]
                != time_series["segment_id"].iloc[i - 1]
            )
        else:
            dt_gap = (times[i] - times[i - 1]) / np.timedelta64(1, "s")
            new_segment = dt_gap > 60.0

        if new_segment:
            state = np.array([meas_x[i], meas_y[i], 0.0, 0.0])
            P = np.diag([sigma_gps**2, sigma_gps**2, 10.0**2, 10.0**2])
            filtered_x[i] = state[0]
            filtered_y[i] = state[1]
            continue

        dt = (times[i] - times[i - 1]) / np.timedelta64(1, "s")
        if dt <= 0:
            filtered_x[i] = state[0]
            filtered_y[i] = state[1]
            continue

        # Constant-velocity transition
        F = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )

        # Discrete white-noise acceleration process noise
        dt2, dt3, dt4 = dt**2, dt**3, dt**4
        q = sigma_process**2
        Q = q * np.array(
            [
                [dt4 / 4, 0.0, dt3 / 2, 0.0],
                [0.0, dt4 / 4, 0.0, dt3 / 2],
                [dt3 / 2, 0.0, dt2, 0.0],
                [0.0, dt3 / 2, 0.0, dt2],
            ]
        )

        # Predict
        state = F @ state
        P = F @ P @ F.T + Q

        # Innovation
        z = np.array([meas_x[i], meas_y[i]])
        innov = z - H @ state
        S = H @ P @ H.T + R

        # Gate check — Mahalanobis distance²
        mahal2 = float(innov @ np.linalg.inv(S) @ innov)
        if mahal2 > gate_chi2:
            excluded[i] = True
            filtered_x[i] = state[0]
            filtered_y[i] = state[1]
            continue

        # Update
        K = P @ H.T @ np.linalg.inv(S)
        state = state + K @ innov
        P = (np.eye(4) - K @ H) @ P

        filtered_x[i] = state[0]
        filtered_y[i] = state[1]

    # Back-project to lat/lon
    filtered_lat = filtered_y / deg_to_m + lat_ref
    filtered_lon = filtered_x / (deg_to_m * np.cos(np.radians(lat_ref))) + lon_ref

    return filtered_lat, filtered_lon, excluded


def speed_from_positions(
    lat: np.ndarray, lon: np.ndarray, times: np.ndarray
) -> np.ndarray:
    """Compute speed in km/h from consecutive positions and timestamps."""
    dist_m = get_distance(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dt_s = np.diff(times) / np.timedelta64(1, "s")
    with np.errstate(invalid="ignore", divide="ignore"):
        speed = np.where(dt_s > 0, dist_m / dt_s * 3.6, np.nan)
    # Prepend NaN for the first sample (no predecessor)
    return np.concatenate([[np.nan], speed])

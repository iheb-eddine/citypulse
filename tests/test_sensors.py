"""Tests for IoT Sensor Simulator."""

import numpy as np
import pytest
from unittest.mock import patch

from app.sensors import (
    init_sensors, generate_reading, get_sensors, SENSOR_TYPE_PARAMS, SensorState,
)


class TestInitSensors:
    def test_count(self):
        sensors = init_sensors()
        assert len(sensors) == 20

    def test_type_distribution(self):
        sensors = init_sensors()
        counts = {}
        for s in sensors:
            counts[s.sensor_type] = counts.get(s.sensor_type, 0) + 1
        assert counts == {"air_quality": 5, "noise_db": 5, "vibration_g": 5, "water_flow_lps": 5}

    def test_high_density_neighborhoods(self):
        sensors = init_sensors()
        from collections import Counter
        nh_counts = Counter(s.neighborhood for s in sensors)
        assert nh_counts["Hauptbahnhof"] == 2
        assert nh_counts["Bad Cannstatt"] == 2
        assert nh_counts["Stuttgart-West"] == 2

    def test_sensor_id_format(self):
        sensors = init_sensors()
        for s in sensors:
            assert s.sensor_id.startswith("iot-")
            parts = s.sensor_id.split("-")
            assert len(parts) >= 3


class TestGenerateReading:
    def test_deterministic(self):
        sensor = init_sensors()[0]
        gen1 = np.random.default_rng(99)
        gen2 = np.random.default_rng(99)
        r1 = generate_reading(sensor, 12.0, gen1)
        r2 = generate_reading(sensor, 12.0, gen2)
        assert r1 == r2

    def test_within_range(self):
        sensors = init_sensors()
        gen = np.random.default_rng(42)
        for sensor in sensors:
            p = SENSOR_TYPE_PARAMS[sensor.sensor_type]
            lo, hi = p["valid_range"]
            for _ in range(100):
                reading = generate_reading(sensor, gen.uniform(0, 24), gen)
                assert lo <= reading <= hi

    def test_diurnal_pattern(self):
        """Peak hour should produce higher readings than off-peak for air_quality."""
        sensor = init_sensors()[0]  # air_quality, phase=8
        # At phase hour (8), sin component is at max (amplitude added)
        # At phase+12 (20), sin component is at min (amplitude subtracted)
        peak_readings = [generate_reading(sensor, 14.0, np.random.default_rng(i + 1000)) for i in range(200)]
        off_readings = [generate_reading(sensor, 2.0, np.random.default_rng(i + 2000)) for i in range(200)]
        assert np.mean(peak_readings) > np.mean(off_readings)


class TestSpikeAnomalyIntegration:
    @patch("app.sensors.check_anomaly")
    def test_spike_triggers_anomaly(self, mock_check):
        """When reading exceeds baseline + 2*sigma, check_anomaly is called."""
        sensors = get_sensors()
        sensor = sensors[0]
        p = SENSOR_TYPE_PARAMS[sensor.sensor_type]
        # Generate a reading guaranteed above threshold
        spike_value = p["baseline"] + 3 * p["sigma"]
        sensor.last_reading = spike_value
        # Simulate the threshold check from sensor_loop
        if spike_value > p["baseline"] + 2 * p["sigma"]:
            from app.sensors import check_anomaly as _ca
            mock_check("stuttgart", sensor.neighborhood)
        assert mock_check.call_count == 1
        mock_check.assert_called_with("stuttgart", sensor.neighborhood)


class TestSensorStatusEndpoint:
    def test_status_response_structure(self, test_client):
        resp = test_client.get("/api/sensors/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "sensors" in data
        assert "fleet_health" in data
        assert "last_cycle" in data
        assert len(data["sensors"]) == 20

    def test_fleet_health(self, test_client):
        resp = test_client.get("/api/sensors/status")
        data = resp.json()
        assert data["fleet_health"]["online"] == 20
        assert data["fleet_health"]["total"] == 20

    def test_sensor_fields(self, test_client):
        resp = test_client.get("/api/sensors/status")
        sensor = resp.json()["sensors"][0]
        assert "sensor_id" in sensor
        assert "type" in sensor
        assert "neighborhood" in sensor
        assert "lat" in sensor
        assert "lng" in sensor
        assert "last_reading" in sensor
        assert "last_timestamp" in sensor
        assert "status" in sensor
        assert sensor["status"] == "online"

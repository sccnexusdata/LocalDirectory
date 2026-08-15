from localdirectory.geospatial import haversine_km, within_radius


def test_lewes_distance():
    assert haversine_km(50.8739, 0.0088, 50.8739, 0.0088) == 0
    assert within_radius(50.8739, 0.0088, 50.8739, 0.0088, 1)

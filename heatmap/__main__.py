from shapely.geometry import Polygon, Point, shape
from shapely.ops import unary_union, transform
import matplotlib.pyplot as plt
from matplotlib import rcParams
import geopandas as gpd
import requests
from pyproj import Transformer
from typing import List
import numpy
import time
from multiprocessing import Pool, cpu_count
import math
from geopy.geocoders import Nominatim
import requests
import json


def get_hsl_polygon() -> Polygon:

    hsl_cities: list[str] = [
        "Helsinki",
        "Espoo",
        "Vantaa",
        "Kauniainen",
        "Siuntio",
        "Kirkkonummi",
        "Sipoo",
        "Kerava",
        "Tuusula",
    ]

    city_boundary_request_address: str = "https://nominatim.openstreetmap.org/search.php?city={}&polygon_geojson=1&format=json&limit=1"

    city_polygons: list[Polygon] = []

    for city in hsl_cities:
        final_request_address: str = city_boundary_request_address.format(city)
        request: requests.models.Response = requests.get(final_request_address)
        city_polygon_data: list[list[list[float]]] = request.json()[0]["geojson"][
            "coordinates"
        ]
        polygon_shell: list[list[float]] = city_polygon_data[0]
        polygon_holes: list[list[float]] = city_polygon_data[1:]
        city_polygon = Polygon(shell=polygon_shell, holes=polygon_holes)
        city_polygons.append(city_polygon)

    hsl_polygon = unary_union(city_polygons)

    return hsl_polygon


def point_within_polygon(params):
    x_min, x_max, y_min, y_max, spacing_in_meters, proxy_polygon_to_intersect = params

    to_original_transformer = Transformer.from_crs("epsg:3857", "epsg:4326")

    number_of_points = (int((x_max - x_min) / spacing_in_meters) + 1) * (
        int((y_max - y_min) / spacing_in_meters) + 1
    )

    gridpoints = numpy.empty(number_of_points, dtype=Point)
    i = 0

    x = x_min
    while x < x_max:
        y = y_min
        while y < y_max:
            p = Point(x, y)
            if proxy_polygon_to_intersect.intersects(p):
                lat, lon = to_original_transformer.transform(x, y)
                gridpoints[i] = Point(lon, lat)
                i = i + 1

            y += spacing_in_meters
        x += spacing_in_meters

    return gridpoints[:i]


def get_point_grid(
    lon_min,
    lat_min,
    lon_max,
    lat_max,
    spacing_in_meters: int,
    polygon_to_intersect: Polygon,
) -> List[Polygon]:
    print("start")
    start = time.time()

    to_proxy_transformer = Transformer.from_crs("epsg:4326", "epsg:3857")

    x_min, y_min = to_proxy_transformer.transform(lat_min, lon_min)
    x_max, y_max = to_proxy_transformer.transform(lat_max, lon_max)

    polygon_transformer = Transformer.from_crs("epsg:4326", "epsg:3857", always_xy=True)
    proxy_polygon_to_intersect = transform(
        polygon_transformer.transform,
        polygon_to_intersect,
    )

    worker_count = cpu_count()

    difference = x_max - x_min
    subintervals = math.floor(difference / spacing_in_meters)
    subintervals_per_interval, excess_subintervals = divmod(subintervals, worker_count)
    interval_lengths = [
        spacing_in_meters * subintervals_per_interval
        + spacing_in_meters * (i < excess_subintervals)
        for i in range(worker_count)
    ]

    intervals = [x_min] * (worker_count + 1)

    for i, interval_length in enumerate(interval_lengths):
        intervals[i + 1] = intervals[i] + interval_length

    interval_pairs = list(zip(intervals[:-1], intervals[1:]))

    parameters = [
        [*xs, y_min, y_max, spacing_in_meters, proxy_polygon_to_intersect]
        for xs in interval_pairs
    ]

    with Pool(worker_count) as pool:
        results = numpy.concatenate(
            pool.map(point_within_polygon, parameters), axis=None, dtype=Point
        )

    end = time.time()
    print("time", end - start)

    return results


def do_the_shit():

    hsl_polygon: Polygon = get_hsl_polygon()

    spacing = 100

    hsl_dot_grid: List[Polygon] = get_point_grid(
        *hsl_polygon.bounds, spacing, hsl_polygon
    )
    print("Amount of points in the polygon:", len(hsl_dot_grid))

    p = gpd.GeoSeries(hsl_polygon)
    p.plot()

    xs = [point.x for point in hsl_dot_grid]
    ys = [point.y for point in hsl_dot_grid]
    plt.scatter(xs, ys, color="orange", s=rcParams["lines.markersize"] ** 0.5)
    plt.show()


def api_for_minutes(minutes):
    api_url = "http://localhost:8080/otp/routers/hsl/isochrone?fromPlace={},{}&mode=WALK,TRAM,TRANSIT,BUS,SUBWAY,RAIL,FERRY&time=4:00pm&date=05-31-2021"
    for minute in minutes:
        api_url = f"{api_url}&cutoffSec={minute*60}"

    return api_url


def plot_heatmap(location):

    api_url = api_for_minutes(range(6, 240, 1))

    featurecollection = requests.get(
        api_url.format(location.latitude, location.longitude)
    ).json()

    with open("temp.txt", "w") as outfile:
        json.dump(featurecollection, outfile, indent=2)

    gdf = gpd.GeoDataFrame.from_features(featurecollection["features"])

    gdf.plot(column="time")


if __name__ == "__main__":
    geolocator = Nominatim(user_agent="Google Maps")
    location = geolocator.geocode("Pietari Kalmin Katu 1, Helsinki, Finland")

    plot_heatmap(location)

    location = geolocator.geocode("Siilitie 8, Helsinki, Finland")

    plot_heatmap(location)

    plt.show()

    exit()

    do_the_shit()

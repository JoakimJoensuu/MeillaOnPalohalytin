from json.decoder import JSONDecodeError
from geopandas.geodataframe import GeoDataFrame
import matplotlib.pyplot as plt
import geopandas as gpd
from geopandas import GeoDataFrame
import requests
from geopy.geocoders import Nominatim
import requests
import json
from typing import List


def api_url_from_for_isochrones(minutes):
    api_url = "http://localhost:8080/otp/routers/hsl/isochrone?fromPlace={},{}&precisionMeters=100&mode=WALK,TRAM,TRANSIT,BUS,SUBWAY,RAIL,FERRY&time=08:00am&date=06-03-2021"
    for minute in minutes:
        api_url = f"{api_url}&cutoffSec={minute*60}"

    return api_url


def api_url_to_for_isochrones(minutes):
    api_url = "http://localhost:8080/otp/routers/hsl/isochrone?toPlace={},{}&fromPlace={},{}&precisionMeters=100&mode=WALK,TRAM,TRANSIT,BUS,SUBWAY,RAIL,FERRY&time=08:00am&date=06-03-2021"
    for minute in minutes:
        api_url = f"{api_url}&cutoffSec={minute*60}"

    return api_url


def get_isochrone(coordinates) -> GeoDataFrame:

    api_url_from = api_url_from_for_isochrones(range(0, 40 + 1, 1))

    featurecollection = requests.get(
        api_url_from.format(
            coordinates.latitude,
            coordinates.longitude,
        )
    ).json()

    gdf_from = gpd.GeoDataFrame.from_features(featurecollection["features"]).dropna()

    gdf_from["time"] = gdf_from["time"].astype(float)

    for i in range(0, len(gdf_from) - 1):
        gdf_from.iloc[[i]] = gpd.overlay(
            gdf_from.iloc[[i]], gdf_from.iloc[[i + 1]], how="difference"
        )

    api_url_to = api_url_to_for_isochrones(range(0, 30 + 1, 1))

    featurecollection = requests.get(
        api_url_to.format(
            coordinates.latitude,
            coordinates.longitude,
            coordinates.latitude,
            coordinates.longitude,
        )
    ).json()

    gdf_to = gpd.GeoDataFrame.from_features(featurecollection["features"]).dropna()

    gdf_to["time"] = gdf_to["time"].astype(float)

    for i in range(0, len(gdf_to) - 1):
        gdf_to.iloc[[i]] = gpd.overlay(
            gdf_to.iloc[[i]], gdf_to.iloc[[i + 1]], how="difference"
        )

    isochrones_union = gdf_to

    isochrone = gdf_from

    isochrones_union = gpd.overlay(
        isochrones_union, isochrone, how="intersection", keep_geom_type=True
    )

    isochrones_union["time"] = isochrones_union["time_1"] + isochrones_union["time_2"]

    isochrones_union["time"] = isochrones_union["time"] / 2

    isochrones_union = isochrones_union.drop(columns=["time_1", "time_2"])

    return isochrones_union


if __name__ == "__main__":
    locations = [
        "Haartmaninkatu 8, 00100 Helsinki",
        "Maarintie 6, 02150 Espoo",
        "Rautatientori, Helsinki",
    ]

    geolocator = Nominatim(user_agent="Google Maps")
    locations_coordinates = [geolocator.geocode(location) for location in locations]

    isochrones: List[GeoDataFrame] = [
        get_isochrone(coordinates) for coordinates in locations_coordinates
    ]

    print("Intersecting isochrones. This will take some time.")

    isochrones_union = isochrones[0]

    for i, isochrone in enumerate(isochrones[1:]):
        isochrones_union = gpd.overlay(
            isochrones_union, isochrone, how="intersection", keep_geom_type=True
        )

        isochrones_union["time_1"] = isochrones_union["time_1"] * (i + 1)

        isochrones_union["time"] = (
            isochrones_union["time_1"] + isochrones_union["time_2"]
        )

        isochrones_union["time"] = isochrones_union["time"] / (i + 2)

        isochrones_union = isochrones_union.drop(columns=["time_1", "time_2"])

    isochrones_union["time"] = isochrones_union["time"] / 60

    isochrones_union = isochrones_union.set_crs("epsg:4326").to_crs("EPSG:3857")

    print(isochrones_union)

    ax = isochrones_union.plot(column="time", legend=True, alpha=0.7, cmap="autumn")

    # 2703424.82,8394314.42,2812118.27,8481605.53
    background = plt.imread("./heatmap/2703424.82,8394314.42,2812118.27,8481605.53.png")
    bbox = [2703424.82, 2812118.27, 8394314.42, 8481605.53]
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])
    ax.imshow(background, zorder=0, extent=bbox, aspect="equal")

    plt.tight_layout()
    plt.show()

    # (24.0082613, 59.7915557, 25.5269348, 60.5806498)
    # for lat: f'{number:.15f}'
    # for lon: f'{number:.13f}'
    # https://render.openstreetmap.org/cgi-bin/export?bbox=24.285278320312504,59.97563121816456,25.26168823242188,60.36567607497561&scale=175000&format=png

    # lon_diff = (25.5230000000000 - 24.0000000000000) / 100
    # lat_diff = (60.59000000000000 - 59.90000000000000) / 100

    # lon_min = 24.0000000000000
    # lat_min = 59.90000000000000
    # lon_max = lon_min + lon_diff
    # lat_max = lat_min + lat_diff

    # while lon_min <= 25.5230000000000:
    #    print(f"{lon_min:.13f}")

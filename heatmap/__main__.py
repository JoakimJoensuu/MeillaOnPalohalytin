import argparse
import decimal
import sys
import time
from argparse import Namespace
from multiprocessing import Lock, Manager, Pool, Process, cpu_count
from multiprocessing.managers import NamespaceProxy
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from geopandas import GeoDataFrame, overlay
from geopy.geocoders import Nominatim
from geopy.location import Location
from matplotlib.axes import Axes
from numpy import add, arange, exp
from PIL import Image
from PIL.PngImagePlugin import PngImageFile
from pyproj import Transformer
from requests import get

ISOCHRONE_REQUEST_BASE_URL = "http://localhost:8080/otp/routers/hsl/isochrone"

ISOCHRONE_REQUEST_URL_PARAMETERS = "&precisionMeters=100&mode=WALK,TRAM,TRANSIT,BUS,SUBWAY,RAIL,FERRY&time=10:00am&date=08-08-2021"


def round_down(value, decimals):
    with decimal.localcontext() as ctx:
        d = decimal.Decimal(value)
        ctx.rounding = decimal.ROUND_DOWN
        return float(round(d, decimals))


def round_up(value, decimals):
    with decimal.localcontext() as ctx:
        d = decimal.Decimal(value)
        ctx.rounding = decimal.ROUND_CEILING
        return float(round(d, decimals))


def plot_heatmap(mean_travel_times: GeoDataFrame) -> Axes:
    geodetic_bounds = mean_travel_times.total_bounds

    geodetic_bounds = (
        round_down(geodetic_bounds[0], 4),
        round_down(geodetic_bounds[1], 4),
        round_up(geodetic_bounds[2], 4),
        round_up(geodetic_bounds[3], 4),
    )

    print(geodetic_bounds)

    images: List[List[PngImageFile]] = []

    token = requests.get("https://www.openstreetmap.org/").cookies.get(
        "_osm_totp_token"
    )

    lon_min = geodetic_bounds[0]
    lat_min = geodetic_bounds[1]

    counter = 0
    step = 0.07

    for lat_max in arange(geodetic_bounds[1], geodetic_bounds[3] + step, step)[1:]:
        row: List[PngImageFile] = []
        for lon_max in arange(geodetic_bounds[0], geodetic_bounds[2] + step, step)[1:]:
            if lat_max > geodetic_bounds[3]:
                lat_max = geodetic_bounds[3]
            if lon_max > geodetic_bounds[2]:
                lon_max = geodetic_bounds[2]

            print(
                f"https://render.openstreetmap.org/cgi-bin/export?bbox={lon_min},{lat_min},{lon_max},{lat_max}&scale=20000&format=png"
            )

            try:
                response = requests.get(
                    f"https://render.openstreetmap.org/cgi-bin/export?bbox={lon_min},{lat_min},{lon_max},{lat_max}&scale=20000&format=png",
                    headers={"Cookie": f"_osm_totp_token={token}"},
                    stream=True,
                )

                response.raise_for_status()
            except requests.exceptions.HTTPError:
                print(response.content)
                exit()

            row.append(Image.open(response.raw))

            print(row[-1].size)

            counter += 1

            lon_min = lon_max
        images.append(row)
        lat_min = lat_max
        lon_min = geodetic_bounds[0]

    width = sum([image.size[0] for image in images[0]])

    height = sum(row[0].size[1] for row in images)

    print(width)
    print(height)

    new_image = Image.new("RGB", (width, height))

    x = 0
    y = 0

    for row in reversed(images):
        for image in row:
            new_image.paste(image, (x, y))

            x += image.size[0]

        y += row[0].size[1]
        x = 0

    mean_travel_times = mean_travel_times.to_crs("EPSG:3857")

    ax = mean_travel_times.plot(
        column="average_time", legend=True, alpha=0.7, cmap="autumn"
    )

    to_mercantor = Transformer.from_crs("EPSG:4326", "EPSG:3857")
    mercantor_bounds = [
        *to_mercantor.transform(geodetic_bounds[1], geodetic_bounds[0]),
        *to_mercantor.transform(geodetic_bounds[3], geodetic_bounds[2]),
    ]

    background = np.asarray(new_image)
    bbox = [
        mercantor_bounds[0],
        mercantor_bounds[2],
        mercantor_bounds[1],
        mercantor_bounds[3],
    ]
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])
    ax.imshow(background, zorder=0, extent=bbox, aspect="equal")

    return ax


def mean_time_calculating_worker(ns: NamespaceProxy, lock: Lock):
    while True:
        lock.acquire()

        if len(ns.travel_times) < 2:
            lock.release()
            return

        first = ns.travel_times[-1]
        second = ns.travel_times[-2]
        ns.travel_times = ns.travel_times[:-2]

        lock.release()

        average_times = overlay(first, second, how="intersection", keep_geom_type=True)

        if len(average_times.index) == 0:
            continue

        average_times["average_time"] = (
            average_times["average_time_1"] * average_times["divider_1"]
            + average_times["average_time_2"] * average_times["divider_2"]
        ) / (average_times["divider_1"] + average_times["divider_2"])

        average_times["divider"] = (
            average_times["divider_1"] + average_times["divider_2"]
        )

        average_times = average_times.drop(
            columns=["average_time_1", "divider_1", "average_time_2", "divider_2"]
        )

        lock.acquire()
        ns.travel_times = ns.travel_times + [average_times]
        lock.release()


def calculate_mean_times(travel_times: GeoDataFrame) -> GeoDataFrame:
    lock = Lock()
    ns: NamespaceProxy = Manager().Namespace()
    ns.travel_times = travel_times

    processes: List[Process] = [
        Process(target=mean_time_calculating_worker, args=(ns, lock))
        for _ in range(cpu_count())
    ]

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    return ns.travel_times[0].drop(columns=["divider"])


def request_isochrone(request_url: str) -> GeoDataFrame:

    print(get(request_url).request)

    isochrone: GeoDataFrame = (
        GeoDataFrame.from_features(get(request_url).json().get("features"))
        .dropna()
        .rename(columns={"time": "average_time"})
        .astype({"average_time": float})
        .set_crs("epsg:4326")
    )

    for i in range(0, len(isochrone.index) - 1):
        isochrone.iloc[[i]] = overlay(
            isochrone.iloc[[i]], isochrone.iloc[[i + 1]], how="difference"
        )

    isochrone["divider"] = 1
    return isochrone


def request_isochrones(request_urls: List[str]) -> List[GeoDataFrame]:
    return Pool(cpu_count()).map(request_isochrone, request_urls)


def url_cutoff_parameters(cutoff_time: int, cutoff_step: int) -> List[str]:
    return "".join(
        [
            f"&cutoffSec={minute*60}"
            for minute in range(0, cutoff_time + cutoff_step, cutoff_step)
        ]
    )


def from_url(coords: Location) -> str:
    return f"{ISOCHRONE_REQUEST_BASE_URL}?fromPlace={coords.latitude},{coords.longitude}{ISOCHRONE_REQUEST_URL_PARAMETERS}"


def to_url(coords: Location) -> str:
    return f"{ISOCHRONE_REQUEST_BASE_URL}?toPlace={coords.latitude},{coords.longitude}&fromPlace={coords.latitude},{coords.longitude}{ISOCHRONE_REQUEST_URL_PARAMETERS}"


def coordinates_to_request_urls(
    locations: List[Location],
    cutoff_time: int,
    cutoff_step: int,
) -> List[str]:
    return [
        url(coords) + url_cutoff_parameters(cutoff_time, cutoff_step)
        for coords in locations
        for url in (from_url, to_url)
    ]


def addresses_to_coordinates(addresses: List[str]) -> List[Location]:
    geolocator: Nominatim = Nominatim(user_agent="Google Maps")
    return [geolocator.geocode(address) for address in addresses]


def main(addresses: List[str], cutoff_time: int, cutoff_step: int) -> None:

    print(f"Got {len(addresses)} places:")
    [print(f"  - {place}") for place in addresses]

    location_coordinates: List[Location] = addresses_to_coordinates(addresses)

    print("Found:")
    [print(f"  - {coordinates}") for coordinates in location_coordinates]

    request_urls: List[str] = coordinates_to_request_urls(
        location_coordinates, cutoff_time, cutoff_step
    )

    print(f"Requesting isochrone data")

    travel_times: List[GeoDataFrame] = request_isochrones(request_urls)

    print("Calculating mean times")

    mean_travel_times: GeoDataFrame = calculate_mean_times(travel_times)

    print("Plotting")

    ax: Axes = plot_heatmap(mean_travel_times)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "addresses",
        type=str,
        nargs="+",
    )
    parser.add_argument("--cutoff-time", type=int, default=30)
    parser.add_argument("--cutoff-step", type=int, default=1)

    args: Namespace = parser.parse_args()

    main(args.addresses, args.cutoff_time, args.cutoff_step)

    plt.show()

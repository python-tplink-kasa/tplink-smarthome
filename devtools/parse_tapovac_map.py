# /// script
# dependencies = [
#   "mashumaro",
#   "pillow",
#   "lz4",
# ]
# ///

"""Simple tool to parse tapovac maps.

Use either get_image(<response for getMapData command>), or
show_image(<path to json file containing the response data).

This script can be also executed directly:

$ uv run parse_tapovac_map.py my_beautiful_getMapData.json

"""

import hashlib
import json
import sys
from base64 import b64decode
from dataclasses import dataclass, field

import lz4.block
from mashumaro import DataClassDictMixin
from PIL import Image, ImageShow


@dataclass
class MapData(DataClassDictMixin):
    """Class representing getMapData response."""

    auto_area_flag: bool
    path_id: int
    version: str
    map_id: int
    resolution: int
    resolution_unit: str
    width: int
    height: int
    origin_coor: tuple[int, int, int]
    real_origin_coor: tuple[int, int, int]
    bitnum: int
    bit_list: dict
    pix_len: int
    map_hash: str
    pix_lz4len: int
    map_data: bytes = field(metadata={"deserialize": b64decode})
    area_list: list


def get_image(data) -> Image:
    """Return image object for getMapData response."""
    data = data["result"]
    d = MapData.from_dict(data)

    # TODO: move assert checks to mashumaro checks

    assert len(d.map_data) == d.pix_lz4len
    assert d.width * d.height == d.pix_len

    print(f"{d.resolution=} {d.resolution_unit}")
    print(f"{d.width=} x {d.height=} = {d.width * d.height} ({d.pix_len=}) {d.bitnum=}")
    print(f"{d.origin_coor=} {d.real_origin_coor=}")
    print(f"{d.auto_area_flag=}")
    print(f"{d.area_list=}")
    print(f"{d.bit_list=}")

    # TODO: handle orientation
    # TODO: parse arealist for rooms/virtualwalls/other
    # TODO: use nicer palette

    img_data = lz4.block.decompress(d.map_data, uncompressed_size=d.pix_len)
    assert d.map_hash == hashlib.md5(img_data).hexdigest().upper()

    assert d.bitnum == 8
    mode = "L"  # L = 8bit gray

    img = Image.frombytes(mode, (d.width, d.height), data=img_data)

    return img


def show_image(filename):
    """Load and show image from getMapData json file."""
    with open(filename) as f:
        data = json.load(f)
        img = get_image(data)
        final = img.resize((4 * img.width, 4 * img.height))
        ImageShow.show(final)


if __name__ == "__main__":
    show_image(sys.argv[1])

"""Implementation for map module."""

import hashlib
import logging
from base64 import b64decode
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mashumaro import DataClassDictMixin, field_options
from mashumaro.config import BaseConfig
from mashumaro.types import Discriminator, SerializationStrategy

from ...exceptions import KasaException
from ...feature import Feature
from ..smartmodule import SmartModule
from .clean import FanSpeed

if TYPE_CHECKING:
    import PIL

_LOGGER = logging.getLogger(__name__)


@dataclass
class MapSummary(DataClassDictMixin):
    """Class representing map summary from mapinfo response."""

    map_id: int
    rotate_angle: int
    is_saved: bool
    update_time: int
    auto_area_flag: bool
    map_locked: int | None = field(default=None)
    global_cleaned: int | None = field(default=None)


class Maps(SerializationStrategy):
    """Strategy to deserialize list of maps into a dict."""

    def deserialize(self, value: str) -> dict:
        """Deserialize list of maps into a dict."""
        maps = {x["map_id"]: MapSummary.from_dict(x) for x in value}
        return maps


@dataclass
class Area(DataClassDictMixin):
    """Reprsentation of an area.

    This can be a room, a carpet, etc.
    """

    class Config(BaseConfig):
        """Configuration."""

        discriminator = Discriminator(
            field="type",
            include_subtypes=True,
        )


@dataclass
class Room(Area):
    """Room area."""

    fanspeed: FanSpeed = field(metadata=field_options(alias="suction"))
    cistern: int = field()  # TODO: enumize

    clean_count: int = field(metadata=field_options(alias="clean_number"))
    id: int
    type: str = "room"


@dataclass
class Carpet(Area):
    """Carpet area."""

    vertexs: list
    carpet_strategy: int
    id: int
    type: str = "carpet_rectangle"


class Areas(SerializationStrategy):
    """Strategy to deserialize list of areas into a dict."""

    def deserialize(self, value: list) -> dict:
        """Deserialize list of areas into a dict."""
        areas = {x["id"]: Area.from_dict(x) for x in value}
        return areas


@dataclass
class MapInfo(DataClassDictMixin):
    """Class representing getMapInfo response."""

    map_num: int
    version: str
    current_map_id: int
    auto_change_map: bool
    maps: dict[int, MapSummary] = field(
        metadata=field_options(serialization_strategy=Maps(), alias="map_list")
    )


@dataclass
class MapData(DataClassDictMixin):
    """Class representing getMapData response."""

    auto_area: bool = field(metadata=field_options(alias="auto_area_flag"))
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
    palette: dict = field(metadata=field_options(alias="bit_list"))
    pix_len: int
    map_hash: str
    pix_lz4len: int
    map_data: bytes = field(metadata={"deserialize": b64decode}, repr=False)
    areas: dict = field(
        metadata=field_options(serialization_strategy=Areas(), alias="area_list")
    )

    def get_image(self, mapinfo: MapInfo | None = None) -> "PIL.Image":
        """Return image object map getMapData response."""
        # TODO: move assert checks to mashumaro checks

        try:
            import lz4.block
            from PIL import Image
        except ImportError as ex:
            raise KasaException(
                "You need to have lz4 and pillow installed to use this function."
            ) from ex

        if len(self.map_data) != self.pix_lz4len:
            raise KasaException("Invalid map data length")

        if self.width * self.height != self.pix_len:
            raise KasaException("Invalid payload")

        _LOGGER.debug("resolution: %s %s", self.resolution, self.resolution_unit)
        _LOGGER.debug("Size: %s x %s", self.width, self.height)
        _LOGGER.debug("Bits per pixel: %s", self.bitnum)
        _LOGGER.debug("origin: %s", self.origin_coor)
        _LOGGER.debug("real origin: %s", self.real_origin_coor)
        for area_id, area in self.areas.items():
            _LOGGER.debug("Area %s: %s", area_id, area)

        _LOGGER.debug("Palette: %s", self.palette)

        # TODO: use nicer palette

        img_data = lz4.block.decompress(self.map_data, uncompressed_size=self.pix_len)

        img_data_hash = hashlib.md5(img_data).hexdigest().upper()  # noqa: S324
        if self.map_hash != img_data_hash:
            raise KasaException("Invalid map hash")

        match self.bitnum:
            case 8:
                mode = "L"  # 8bit gray
            case _:
                raise KasaException(f"Unknown bitnum {self.bitnum}")

        img = Image.frombytes(mode, (self.width, self.height), data=img_data)

        # rotate
        img = img.rotate(mapinfo.maps[self.map_id].rotate_angle)

        return img


@dataclass
class PathData(DataClassDictMixin):
    """Path data container."""

    path_id: int
    points: int = field(metadata=field_options(alias="point_counts"))
    total_points: int
    data: bytes = field(
        metadata=field_options(deserialize=b64decode, alias="pos_array"), repr=False
    )
    data_len: int = field(metadata=field_options(alias="pos_len"))
    data_lz4len: int = field(metadata=field_options(alias="pos_lz4len"))

    def get_decompressed_data(self) -> bytes:
        """Return decompressed path data."""
        try:
            import lz4.block
        except ImportError as ex:
            raise KasaException(
                "You need to have lz4 and pillow installed to use this function."
            ) from ex

        decompressed = lz4.block.decompress(self.data, uncompressed_size=self.data_len)
        if len(decompressed) != self.data_len:
            raise KasaException("Invalid data length")

        return decompressed


class Map(SmartModule):
    """Implementation of vacuum map module."""

    REQUIRED_COMPONENT = "map"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getMapInfo": {},
            "getMapData": {"map_id": -1},
            "getPathData": {"start_pos": 0},
        }

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="map_count",
                name="Map count",
                container=self,
                attribute_getter="map_count",
                category=Feature.Category.Debug,
                type=Feature.Sensor,
            )
        )

    @property
    def map_count(self) -> int:
        """Return number of maps."""
        return self.map_info.map_num

    @property
    def map_info(self) -> MapInfo:
        """Return map information."""
        return MapInfo.from_dict(self.data["getMapInfo"])

    @property
    def map_data(self) -> MapData:
        """Return map data."""
        return MapData.from_dict(self.data["getMapData"])

    @property
    def path_data(self) -> PathData:
        """Return path data."""
        return PathData.from_dict(self.data["getPathData"])

    def get_path(self) -> bytes:
        """Return path as an image."""
        return self.path_data.get_decompressed_data()

    def get_map_image(self) -> "PIL.Image":
        """Return map as an image."""
        return self.map_data.get_image(self.map_info)

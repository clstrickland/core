"""Define data type used by coordinator."""

from dataclasses import dataclass

from songpal.containers import SettingCandidate


@dataclass
class InputInfo:
    """Represents a single input source."""

    uri: str
    title: str


@dataclass
class VolumeInfo:
    """Represents volume information for a zone."""

    min: int
    max: int
    step: int
    mute: str  # Could also be a bool if you convert it
    volume: int


@dataclass
class ZoneInfo:
    """Represents all information for a single zone."""

    title: str
    active: bool
    source: str | None
    volume_info: VolumeInfo | None
    inputs: list[InputInfo]
    id: str


@dataclass
class SongpalData:
    """Represents all data for the Songpal coordinator."""

    model: str
    zones: dict[str, ZoneInfo]
    sound_modes: dict[str, SettingCandidate]
    active_sound_mode: str | None

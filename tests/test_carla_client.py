from __future__ import annotations

from app.executor.carla_client import CarlaClient


class FakeMap:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeWorld:
    def __init__(self, map_name: str) -> None:
        self._map = FakeMap(map_name)

    def get_map(self) -> FakeMap:
        return self._map


class FakeClient:
    def __init__(self, available_maps: list[str], loaded_world: FakeWorld) -> None:
        self._available_maps = available_maps
        self._loaded_world = loaded_world
        self.load_world_calls: list[str] = []

    def get_available_maps(self) -> list[str]:
        return list(self._available_maps)

    def load_world(self, map_name: str) -> FakeWorld:
        self.load_world_calls.append(map_name)
        return self._loaded_world


def test_load_map_skips_reload_when_current_world_matches() -> None:
    client = CarlaClient("127.0.0.1", 2000, 10.0, 8010)
    fake_client = FakeClient(
        available_maps=["Carla/Maps/Town10HD_Opt"],
        loaded_world=FakeWorld("Carla/Maps/Town10HD_Opt"),
    )
    client._client = fake_client
    client._world = FakeWorld("Carla/Maps/Town10HD_Opt")

    resolved = client.load_map("Town10HD_Opt")

    assert resolved == "Carla/Maps/Town10HD_Opt"
    assert fake_client.load_world_calls == []


def test_load_map_reloads_when_current_world_differs() -> None:
    client = CarlaClient("127.0.0.1", 2000, 10.0, 8010)
    loaded_world = FakeWorld("Carla/Maps/Town10HD_Opt")
    fake_client = FakeClient(
        available_maps=["Carla/Maps/Town10HD_Opt", "Carla/Maps/Town01"],
        loaded_world=loaded_world,
    )
    client._client = fake_client
    client._world = FakeWorld("Carla/Maps/Town01")

    resolved = client.load_map("Town10HD_Opt")

    assert resolved == "Carla/Maps/Town10HD_Opt"
    assert fake_client.load_world_calls == ["Carla/Maps/Town10HD_Opt"]
    assert client._world is loaded_world

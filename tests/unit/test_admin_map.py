import pytest
from fastapi import HTTPException

from app.routers.admin import _validate_map_geometry
from app.schemas import MapObject, OfficeMap


def _workplace(**kwargs) -> MapObject:
  defaults = {
      "id": "wp-1",
      "type": "workplace",
      "x": 100,
      "y": 100,
      "width": 80,
      "height": 60,
      "label": "Окно 1",
      "window_id": 1,
  }
  defaults.update(kwargs)
  return MapObject(**defaults)


def test_validate_map_geometry_accepts_valid_map():
    data = OfficeMap(
        width=1200,
        height=700,
        objects=[_workplace()],
    )
    _validate_map_geometry(data)


def test_validate_map_geometry_rejects_small_canvas():
    data = OfficeMap(width=300, height=700, objects=[])
    with pytest.raises(HTTPException) as exc:
        _validate_map_geometry(data)
    assert exc.value.status_code == 400


def test_validate_map_geometry_rejects_duplicate_ids():
    data = OfficeMap(
        width=1200,
        height=700,
        objects=[_workplace(id="dup"), _workplace(id="dup", x=200)],
    )
    with pytest.raises(HTTPException) as exc:
        _validate_map_geometry(data)
    assert "ID" in exc.value.detail


def test_validate_map_geometry_rejects_window_on_non_workplace():
    data = OfficeMap(
        width=1200,
        height=700,
        objects=[
            MapObject(
                id="wall-1",
                type="wall",
                x=0,
                y=0,
                width=20,
                height=20,
                window_id=1,
            )
        ],
    )
    with pytest.raises(HTTPException) as exc:
        _validate_map_geometry(data)
    assert "привязать" in exc.value.detail


def test_validate_map_geometry_rejects_out_of_bounds():
    data = OfficeMap(
        width=1200,
        height=700,
        objects=[_workplace(x=1150, width=100)],
    )
    with pytest.raises(HTTPException) as exc:
        _validate_map_geometry(data)
    assert "границы" in exc.value.detail

"""Leaflet helper script for GHSCI map, drawing on NiceGUI example."""

from typing import Tuple

from nicegui import ui


class leaflet(ui.element, component='leaflet.js'):
    """Leaflet helper script for GHSCI map, drawing on NiceGUI example."""

    def __init__(self) -> None:
        super().__init__()
        ui.add_head_html(
            """<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
     integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
     crossorigin=""/>""",
        )
        ui.add_head_html(
            """<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
     integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
     crossorigin=""></script>""",
        )

    def set_location(self, location: Tuple[float, float], zoom: int) -> None:
        """Place marker and set the map location and zoom level."""
        self.run_method('set_location', location[0], location[1], zoom)

    def set_no_location(
        self, location: Tuple[float, float], zoom: int,
    ) -> None:
        """Set the map location and zoom level, without placing a marker."""
        self.run_method('set_view', location[0], location[1], zoom)

    def add_geojson(
        self,
        geojson,
        hex_colour='#000000',
        opacity=0.5,
        fillOpacity=0.1,
        remove=True,
    ) -> None:
        """Add a GeoJSON layer to the map."""
        self.run_method(
            'add_geojson', geojson, hex_colour, opacity, fillOpacity, remove,
        )

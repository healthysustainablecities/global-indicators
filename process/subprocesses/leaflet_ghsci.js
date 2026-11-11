export default {
  template: "<div></div>",
  mounted() {
    this.map = L.map(this.$el);
    // Keyless providers (CARTO basemaps now require an API key). Satellite
    // imagery matches the report maps (contextily Esri.WorldImagery); both
    // layers are shown in grayscale by the .leaflet-tile filter in leaflet.py.
    this.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      bounds: [
        [-90, -180],
        [90, 180]
      ],
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    }).addTo(this.map);
    this.osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      bounds: [
        [-90, -180],
        [90, 180]
      ],
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });
    L.control.scale().addTo(this.map);
    this.baseMaps = {
      "Satellite": this.satellite,
      "OpenStreetMap": this.osm,
    };
    this.layerControl = L.control.layers(this.baseMaps).addTo(this.map);
  },
  methods: {
    set_location(latitude, longitude, zoom = 9) {
      this.target = L.latLng(latitude, longitude);
      this.map.setView(this.target, zoom);
      if (this.marker) {
        this.map.removeLayer(this.marker);
      }
      this.marker = L.marker(this.target);
      this.marker.addTo(this.map);
    },
    set_view(latitude, longitude, zoom = 3) {
      if (this.marker) {
        this.map.removeLayer(this.marker);
      }
      this.map.setView([latitude,longitude], zoom);
    },
    // get_selected() {
    //   return this.selected;
    // },
     add_geojson(polygons,hex_colour,opacity, fillOpacity,remove,zoom) {
      if (remove) {
        if (this.geojson) {
          this.map.removeLayer(this.geojson);
        }
      }
      this.geojson = L.geoJson(polygons, {
        style: function (feature) {
          return {
            color: hex_colour,
            weight: 3,
            opacity: opacity,
            fillColor: hex_colour,
            fillOpacity: fillOpacity,
            interactive: true,
          };
        },
        onEachFeature: function (feature, layer) {
          if (feature.properties && feature.properties.db) {
            layer.bindTooltip(feature.properties.db, {
              permanent: false,
              opacity: 0.8
            });
          }
        }
      }).addTo(this.map);

      if (zoom) {
        this.map.fitBounds((this.geojson).getBounds());
      }
    },
  },
};

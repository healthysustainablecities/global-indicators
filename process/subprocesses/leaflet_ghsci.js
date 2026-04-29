export default {
  template: "<div></div>",
  mounted() {
    this.map = L.map(this.$el);
    this.osm = L.tileLayer("http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", {
      bounds: [
        [-90, -180],
        [90, 180]
      ],
      attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | &copy; <a href="http://cartodb.com/attributions">CartoDB</a>',
    }).addTo(this.map);
    this.satellite = L.tileLayer.wms("https://tiles.maps.eox.at/wms", {
      bounds: [
        [-90, -180],
        [90, 180]
      ],
      layers: 's2cloudless-2020_3857',
      attribution: '<a href="https://s2maps.eu">Sentinel-2 cloudless - https://s2maps.eu</a> by <a href="https://eox.at/">EOX IT Services GmbH</a><p>(Contains modified Copernicus Sentinel data 2020), under CC-BY-NC-SA 4.0 licence.',
    });
    L.control.scale().addTo(this.map);
    this.baseMaps = {
      "OpenStreetMap": this.osm,
      "Satellite": this.satellite,
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

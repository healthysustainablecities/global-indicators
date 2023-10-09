export default {
  template: "<div></div>",
  mounted() {
    this.map = L.map(this.$el);
    L.control.scale().addTo(this.map);
    // L.tileLayer("http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", {
    //   attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | &copy; <a href="http://cartodb.com/attributions">CartoDB</a>',
    // }).addTo(this.map);
    L.tileLayer.wms("https://tiles.maps.eox.at/wms", {
      layers: 's2cloudless-2020_3857',
      attribution: '<a href="https://s2maps.eu">Sentinel-2 cloudless - https://s2maps.eu</a> by <a href="https://eox.at/">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data 2020), under CC-BY-NC-SA 4.0 licence.',
    }).addTo(this.map);
    // L.tileLayer.wms("https://tiles.maps.eox.at/wms", {
    //   layers: 'overlay_base_3857',
    //   attribution: '<a href="https://maps.eox.at">Overlay</a> { Data &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Rendering &copy; <a href="https://eox.at">EOX</a> and <a href="https://github.com/mapserver/basemaps">MapServer</a>',
    // }).addTo(this.map);
    // this.selected = [];
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
    add_geojson(polygons,hex_colour,opacity, fillOpacity,remove) {
      // console.log("add_geojson", polygons);
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
          };
        },
        // onEachFeature: function (feature, layer) {
        //   layer.on('click', function (e) {
        //     this.selected = [e.target.feature.properties.db];
        //     // console.log(db);
        //   });
        //   // var table = '<table class="geojson-table" width="470" height="300"><col width="550"><col width="290"><col width="80"><col width="80"><tbody>'
        //   // // var table = '<table class="geojson-table"><tbody>'
        //   // for (var key in layer.feature.properties) {
        //   //   var row = typeof(layer.feature.properties[key])=='number'? layer.feature.properties[key].toFixed(1) : layer.feature.properties[key]
        //   //   table = table+'<tr><td><b>'+key+'</b>: '+row+'</td></tr>'
        //   // }
        //   // table = table+'</tbody></table>'
        //   // layer.bindPopup(table,{maxHeight: 300, minWidth: 490, opacity: 0.5});
        // }
      }
      //   ).bindTooltip(function (layer) {
    //     return layer.feature.properties; //merely sets the tooltip text
    //  }, {permanent: true, opacity: 0.5}  //then add your options
    // ).bindTooltip(
    //   'Click to view region summary'
      ).addTo(
            this.map
            );
    this.map.fitBounds((this.geojson).getBounds());
  }
  },
};

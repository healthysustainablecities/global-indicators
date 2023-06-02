export default {
  template: "<div></div>",
  mounted() {
    this.map = L.map(this.$el);
    L.control.scale().addTo(this.map);
    L.tileLayer("http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | &copy; <a href="http://cartodb.com/attributions">CartoDB</a>',
    }).addTo(this.map);
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
      // console.log("set_location", latitude, longitude, zoom);
    },
    set_view(latitude, longitude, zoom = 3) {
      this.map.setView([latitude,longitude], zoom);
      if (this.marker) {
        this.map.removeLayer(this.marker);
      }
      // console.log("set_location", latitude, longitude, zoom);
    },
  },
};

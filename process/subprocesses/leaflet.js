export default {
  template: "<div></div>",
  mounted() {
    this.map = L.map(this.$el);
    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap contributors</a>',
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

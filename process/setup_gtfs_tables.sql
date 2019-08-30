DROP TABLE IF EXISTS agency CASCADE;
CREATE TABLE agency
(
  agency_id         text UNIQUE NULL,
  agency_name       text NOT NULL,
  agency_url        text NOT NULL,
  agency_timezone   text NOT NULL,
  agency_lang       text NULL
);

DROP TABLE IF EXISTS calendar CASCADE;
CREATE TABLE calendar
(
  service_id        text PRIMARY KEY,
  monday            boolean NOT NULL,
  tuesday           boolean NOT NULL,
  wednesday         boolean NOT NULL,
  thursday          boolean NOT NULL,
  friday            boolean NOT NULL,
  saturday          boolean NOT NULL,
  sunday            boolean NOT NULL,
  start_date        numeric(8) NOT NULL,
  end_date          numeric(8) NOT NULL
);

DROP TABLE IF EXISTS calendar_dates CASCADE;
CREATE TABLE calendar_dates
(
  service_id text NOT NULL,
  date numeric(8) NOT NULL,
  exception_type integer NOT NULL
);

DROP TABLE IF EXISTS routes CASCADE;
CREATE TABLE routes
(
  route_id          text PRIMARY KEY,
  route_short_name  text NULL,
  route_long_name   text NOT NULL,
  route_desc        text NULL,
  route_type        integer NULL,
  route_url         text NULL
);

DROP TABLE IF EXISTS shapes CASCADE;
CREATE TABLE shapes
(
  shape_id          text,
  shape_pt_lat      wgs84_lat NOT NULL,
  shape_pt_lon      wgs84_lon NOT NULL,
  shape_pt_sequence integer NOT NULL
);


DROP TABLE IF EXISTS stop_times CASCADE;
CREATE TABLE stop_times
(
  trip_id           text NOT NULL,
  arrival_time      interval NOT NULL,
  departure_time    interval NOT NULL,
  stop_id           text NOT NULL,
  stop_sequence     integer NOT NULL,
  pickup_type       integer NULL CHECK(pickup_type >= 0 and pickup_type <=3),
  drop_off_type     integer NULL CHECK(drop_off_type >= 0 and drop_off_type <=3),
  timepoint         integer NULL
);

DROP TABLE IF EXISTS stops CASCADE;
CREATE TABLE stops
(
  stop_id           text PRIMARY KEY,
  stop_code         text NULL,
  stop_name         text NOT NULL,
  stop_desc     	text NULL,
  stop_lat          wgs84_lat NOT NULL,
  stop_lon          wgs84_lon NOT NULL,
  zone_id           text NULL,
  stop_url          text NULL,
  location_type     text NULL,
  parent_station    text NULL,
  district          text NULL
);

DROP TABLE IF EXISTS trips CASCADE;
CREATE TABLE trips
(
  route_id          text NOT NULL,
  service_id        text NOT NULL,
  trip_id           text NOT NULL PRIMARY KEY,
  trip_headsign     text NULL,
  direction_id      boolean NULL,
  block_id          text NULL,
  shape_id          text NULL
);


copy public.agency from '{agency}' with csv header;
copy public.calendar from '{calendar}' with csv header;
copy public.calendar_dates from '{calendar_dates}' with csv header;
copy public.routes from '{routes}' with csv header;
copy public.shapes from '{shapes}' with csv header;
copy public.stop_times from '{stop_times}' with csv header;
copy public.stops from '{stops}' with csv header;
copy public.trips from '{trips}' with csv header
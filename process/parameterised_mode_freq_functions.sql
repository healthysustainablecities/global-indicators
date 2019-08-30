CREATE OR REPLACE FUNCTION {mode}_{interval_short}_stops(date) RETURNS SETOF text AS $$
DECLARE
  service_date ALIAS FOR $1;
BEGIN

DROP TABLE IF EXISTS stop_departure_{mode} CASCADE;
CREATE TABLE stop_departure_{mode} AS
SELECT DISTINCT
  routes.route_id,
  route_type,
  trips.trip_id,
  stops.stop_id,
  stop_sequence,
  departure_time
FROM  
  routes,
  trips,
  stop_times,
  stops,
  calendar_series
WHERE
  routes.route_id = trips.route_id AND
  trips.service_id = calendar_series.service_id AND
  stop_times.trip_id = trips.trip_id AND
  stop_times.stop_id = stops.stop_id AND
  -- daytime {mode} services
  stop_times.departure_time BETWEEN '{start_time}' AND '{end_time}' AND
  routes.route_type IN ({route_types}) AND
  -- offered on service_date
  calendar_series.date = to_number(to_char(service_date, 'YYYYMMDD'), '99999999')
  -- custom clause, for example: routes.agency_id  IN ('1','2') 
  {custom_mode}
ORDER BY
  trip_id,
  stop_sequence;

DROP MATERIALIZED VIEW IF EXISTS stop_departure_intervals_{mode} CASCADE;
CREATE MATERIALIZED VIEW stop_departure_intervals_{mode} AS
SELECT
  stop_id,
  departure_time,
  lag(departure_time) OVER (PARTITION BY stop_id ORDER BY departure_time DESC) as next_departure_time
FROM
  stop_departure_{mode}
ORDER BY
  stop_id,
  departure_time;

-- Find earliest stop after start time
CREATE OR REPLACE VIEW stop_first_peak_service_{mode} AS
SELECT 
  stop_id,
  MIN (departure_time)
FROM 
  stop_departure_intervals_{mode}
GROUP BY
  stop_id
ORDER BY
  stop_id;

-- Find stops with a peak service commencement before buffer start
CREATE OR REPLACE VIEW stop_first_service_before_{buffer_start_short}_{mode} AS
SELECT
  stop_id
FROM
  stop_first_peak_service_{mode}
WHERE
  min <= '{buffer_start}';

-- Find latest stop before end time
CREATE OR REPLACE VIEW stop_last_peak_service_{mode} AS
SELECT 
  stop_id,
  MAX (departure_time)
FROM 
  stop_departure_intervals_{mode}
GROUP BY
  stop_id
ORDER BY
  stop_id;

-- Find stops with a peak service after buffer end 
CREATE OR REPLACE VIEW stop_last_service_after_{buffer_end_short}_{mode} AS
SELECT
  stop_id
FROM
  stop_last_peak_service_{mode}
WHERE
  max >= '{buffer_end}';

-- Find maximum interval between services for stops with a service before 7.30am and after 6.30pm 
CREATE OR REPLACE VIEW stop_max_interval_{mode} AS
SELECT 
  s.stop_id, 
  MAX (s.next_departure_time - s.departure_time) AS max_interval
FROM 
  stop_departure_intervals_{mode} AS s,
  stop_first_service_before_{buffer_start_short}_{mode} AS f,
  stop_last_service_after_{buffer_end_short}_{mode} AS l
WHERE
  s.next_departure_time IS NOT NULL AND
  s.stop_id = f.stop_id AND
  s.stop_id = l.stop_id
GROUP BY
  s.stop_id
ORDER BY
  s.stop_id;

DROP TABLE IF EXISTS stop_{interval_short}_{mode};
CREATE TABLE stop_{interval_short}_{mode} AS
SELECT 
  s.route_type,
  s.stop_id,
  s.stop_name,
  s.stop_lat, 
  s.stop_lon,
  (SELECT EXTRACT(epoch FROM i.max_interval)/60) AS max_interval
FROM
  stop_{mode} AS s,
  stop_max_interval_{mode} AS i 
WHERE 
  s.stop_id = i.stop_id AND
  i.max_interval <= '{interval}';

RETURN QUERY SELECT stop_id FROM stop_{interval_short}_{mode};
  
END;
$$ LANGUAGE plpgsql;
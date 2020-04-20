--------------------
-- Calendar setup -- 
--------------------

-- needed for crosstab calculations later
-- CREATE EXTENSION tablefunc;

-- this generates the series of dates (and dow) for all dates covered by the calendar
DROP TABLE IF EXISTS calendar_extent;
CREATE TABLE calendar_extent AS
SELECT
  to_number(to_char(date, 'YYYYMMDD'), '99999999') AS date_numeric,
  extract(dow from date)::int AS dow
FROM
  generate_series (
    (SELECT to_date(to_char(MIN(start_date), '99999999'), 'YYYYMMDD') FROM calendar),
    (SELECT to_date(to_char(MAX(end_date), '99999999'), 'YYYYMMDD') FROM calendar),
  interval '1 day'
  ) date;
  

-- this generates a table that summarises the maximum number of days a stop_id could be a 30 minute stop by dow
DROP TABLE IF EXISTS calendar_maximum;
CREATE TABLE calendar_maximum AS
SELECT * FROM crosstab (
  'SELECT DISTINCT
    stop_id,
    dow,
    count(date_numeric) dow_count
  FROM
    stops,
    calendar_extent
  GROUP BY
    stop_id,
    dow
  ORDER BY
    stop_id ASC,
    dow ASC',
  'SELECT * FROM generate_series(0, 6) ORDER BY 1'
)
  AS (
    stop_id text,
  sunday int,
  monday int,
  tuesday int,
  wednesday int,
  thursday int,
  friday int,
  saturday int
)
;

-- this function generates a series of dates between two days  
CREATE OR REPLACE FUNCTION dayseries (date, date)
  RETURNS SETOF timestamp with time zone AS
$$
  SELECT * FROM generate_series($1, $2, interval '1d') d
$$ LANGUAGE SQL IMMUTABLE;

-- this generates a service_id and a series of dates corresponding to the calendar
DROP TABLE IF EXISTS calendar_series;
CREATE TABLE calendar_series AS
SELECT
  service_id,
  to_number(to_char(dayseries(to_date(to_char(start_date, '99999999'), 'YYYYMMDD'), to_date(to_char(end_date, '99999999'), 'YYYYMMDD'))::date, 'YYYYMMDD'), '99999999') AS date
FROM
  calendar
ORDER BY
  service_id,
  date;

ALTER TABLE calendar_series ADD COLUMN dow integer;
UPDATE calendar_series SET dow = extract(dow from to_date(to_char(date, '99999999'), 'YYYYMMDD'))::int;

-- this deletes from the series dates on which the named day is "false"
DELETE FROM calendar_series
WHERE (service_id, dow) IN (
  SELECT
    service_id,
    dow
  FROM (
    SELECT
      service_id,
      unnest(
        array[1, 2, 3, 4, 5, 6, 0]
      ) AS dow,
      unnest(
        array[monday, tuesday, wednesday, thursday, friday, saturday, sunday]
      ) AS operates
    FROM calendar) s
  WHERE
    operates = 'F');
  
-- this deletes services as required based on the calendar_dates table
DELETE FROM calendar_series
WHERE (service_id, date) IN (SELECT service_id, date FROM calendar_dates WHERE exception_type = '2');

-- this adds services as required based on the calendar_dates table
INSERT INTO calendar_series SELECT service_id, date, extract(dow from to_date(to_char(date, '99999999'), 'YYYYMMDD'))::int FROM calendar_dates WHERE exception_type = '1';


--------------------------------------------------
-- Create train, tram and bus (and coach) stops --
--------------------------------------------------

SELECT
  route_type
FROM
  routes
GROUP BY
  route_type
ORDER BY
  route_type;


DROP TABLE IF EXISTS stop_{mode};
CREATE TABLE stop_{mode} AS
SELECT
  routes.route_type,
  stops.stop_id,
  stops.stop_name,
  stops.stop_lat,
  stops.stop_lon
FROM
  public.stops,
  public.stop_times,
  public.trips,
  public.routes
WHERE 
  stops.stop_id = stop_times.stop_id AND
  stop_times.trip_id = trips.trip_id AND
  trips.route_id = routes.route_id AND
  -- allow for consideration of both metropolitan and regional trains
  routes.route_type IN ({route_types})
  {custom_mode}
GROUP BY
  routes.route_type,
  stops.stop_id,
  stops.stop_name,
  stops.stop_lat,
  stops.stop_lon
ORDER BY
  stops.stop_id;

-- after the stored procedures have been defined, this generates the dates for each stop_id where that stop_id provides a 30 minute frequency service
DROP TABLE IF EXISTS {mode}_{interval_short}_stops_by_date;
CREATE TABLE {mode}_{interval_short}_stops_by_date AS
SELECT DISTINCT
  date_numeric,
  {mode}_{interval_short}_stops(to_date(to_char(date_numeric, '99999999'), 'YYYYMMDD')) stop_id
FROM
  calendar_extent
ORDER BY
  date_numeric;
  
-- view the results
SELECT
  date_numeric,
  count(stop_id)
FROM
  (SELECT DISTINCT * FROM {mode}_{interval_short}_stops_by_date) t
GROUP BY
  date_numeric
ORDER BY
  date_numeric;

-- create the crosstab query
DROP TABLE IF EXISTS {mode}_{interval_short}__stop_dow;
DROP TABLE IF EXISTS {mode}_{interval_short}_stop_dow;
CREATE TABLE {mode}_{interval_short}_stop_dow AS
SELECT * FROM crosstab (
  'SELECT DISTINCT
    stop_id,
    extract(dow from to_date(to_char(date_numeric, ''99999999''), ''YYYYMMDD''))::int AS dow,
  count(date_numeric) dow_count
  FROM
    (SELECT DISTINCT * FROM {mode}_{interval_short}_stops_by_date) t
  -- exclude school holiday periods and data issues whereby core rail services are not in the timetable from ?
  WHERE
    date_numeric BETWEEN {start_date} AND {end_date}
  GROUP BY
    stop_id,
    dow
  ORDER BY
    stop_id,
    dow',
  'SELECT * FROM generate_series(0, 6) ORDER BY 1'
)
  AS (
    stop_id text,
  sunday int,
  monday int,
  tuesday int,
  wednesday int,
  thursday int,
  friday int,
  saturday int
);

-- this generates a table that summarises the maximum number of days a stop_id could be a frequent stop by dow
DROP TABLE IF EXISTS calendar_{mode}_maximum;
CREATE TABLE calendar_{mode}_maximum AS
SELECT * FROM crosstab (
  'SELECT DISTINCT
    stop_id,
    dow,
    count(date_numeric) dow_count
  FROM
    stops,
    calendar_extent
  WHERE
    date_numeric BETWEEN {start_date} AND {end_date}
  GROUP BY
    stop_id,
    dow
  ORDER BY
    stop_id ASC,
    dow ASC',
  'SELECT * FROM generate_series(0, 6) ORDER BY 1'
)
  AS (
    stop_id text,
  sunday int,
  monday int,
  tuesday int,
  wednesday int,
  thursday int,
  friday int,
  saturday int
);

DROP TABLE IF EXISTS {mode}_{interval_short}_stop_pcent;
CREATE TABLE {mode}_{interval_short}_stop_pcent AS
SELECT
  b.stop_id,
  100*(coalesce(b.monday,0) + coalesce(b.tuesday,0) + coalesce(b.wednesday,0) + coalesce(b.thursday,0) + coalesce(b.friday,0))/(m.monday + m.tuesday + m.wednesday + m.thursday + m.friday)::decimal weekday_pcent
FROM
  {mode}_{interval_short}_stop_dow b INNER JOIN calendar_{mode}_maximum m ON b.stop_id = m.stop_id;

DROP TABLE IF EXISTS {mode}_{interval_short}_stop_final;
CREATE TABLE {mode}_{interval_short}_stop_final AS
SELECT DISTINCT
  s.route_type,
  s.stop_id,
  s.stop_name,
  s.stop_lat, 
  s.stop_lon
FROM
  stop_{mode} s,
  {mode}_{interval_short}_stop_pcent p
WHERE 
  s.stop_id = p.stop_id AND
  p.weekday_pcent > 90;
SELECT a.mb_code_20 AS mb_code_2016, 
        AVG(distance) AS mean, 
        stddev_samp(distance) AS sd,
        min(distance) AS min,
        max(distance) AS max,
        c.dwelling,
        c.person
 FROM parcel_dwellings a 
 LEFT JOIN od_closest b ON a.gnaf_pid = b.gnaf_pid 
 LEFT JOIN abs_linkage c ON a.mb_code_20 = c.mb_code_2016
 WHERE dest = 13 GROUP BY (a.mb_code_20, c.dwelling, c.person) 
 LIMIT 20

CREATE EXTENSION "tablefunc"; 
 
DROP TABLE IF EXISTS sim_dwellings_access_train;
CREATE TABLE sim_dwellings_access_train AS
SELECT t.mb_code_2016, mean, sd, min, max, t.dwelling, t.person, normal_rand(t.dwelling::int, mean::float8, sd::float8) AS sim_access
FROM 
(SELECT a.mb_code_20 AS mb_code_2016, 
        AVG(distance) AS mean, 
        stddev_samp(distance) AS sd,
        min(distance) AS min,
        max(distance) AS max,
        c.dwelling,
        c.person
 FROM parcel_dwellings a 
 LEFT JOIN od_closest b ON a.gnaf_pid = b.gnaf_pid 
 LEFT JOIN abs_linkage c ON a.mb_code_20 = c.mb_code_2016
 WHERE dest = 13 GROUP BY (a.mb_code_20, c.dwelling, c.person)) t;

SELECT 
  100*(SELECT COUNT(*) FROM sim_dwellings_access_train WHERE mean <= 1000)/(SELECT COUNT(*) FROM sim_dwellings_access_train)::float AS percent_mean,
  100*(SELECT COUNT(*) FROM sim_dwellings_access_train WHERE sim_access <= 1000)/(SELECT COUNT(*) FROM sim_dwellings_access_train)::float AS percent_sim;
SELECT min(mean) AS min_mean, min(sim_access) AS min_sim FROM sim_dwellings_access_train;

CREATE OR REPLACE FUNCTION normal_rand_limit(testval double precision, mean numeric, sd numeric, minval numeric, maxval numeric) RETURNS numeric AS
$$
DECLARE
    draw numeric;
BEGIN
   IF testval >= minval AND testval <= maxval THEN 
     RETURN testval;
   ELSIF mean  < minval OR mean > maxval THEN 
     RETURN -999;
   ELSE
     draw := normal_rand(1 , mean , sd);
     WHILE draw < minval OR draw > maxval LOOP
       draw := normal_rand(1 , mean , sd);
     END LOOP;
     RETURN draw;
   END IF;
END;
$$ language 'plpgsql' STRICT;


DROP TABLE IF EXISTS sim_dwellings_access_train;
CREATE TABLE sim_dwellings_access_train AS
SELECT t.mb_code_2016, mean, sd, min, max, t.dwelling, t.person, normal_rand_limit(normal_rand(t.dwelling::int, mean::float8, sd::float8), mean, sd, min, max ) AS sim_access
FROM 
(SELECT a.mb_code_20 AS mb_code_2016, 
        AVG(distance) AS mean, 
        stddev_samp(distance) AS sd,
        min(distance) AS min,
        max(distance) AS max,
        c.dwelling,
        c.person
 FROM parcel_dwellings a 
 LEFT JOIN od_closest b ON a.gnaf_pid = b.gnaf_pid 
 LEFT JOIN abs_linkage c ON a.mb_code_20 = c.mb_code_2016
 WHERE dest = 13 GROUP BY (a.mb_code_20, c.dwelling, c.person)) t;

SELECT 
  100*(SELECT COUNT(*) FROM sim_dwellings_access_train WHERE mean <= 1000)/(SELECT COUNT(*) FROM sim_dwellings_access_train)::float AS percent_mean,
  100*(SELECT COUNT(*) FROM sim_dwellings_access_train WHERE sim_access <= 1000)/(SELECT COUNT(*) FROM sim_dwellings_access_train)::float AS percent_sim;
SELECT min(mean) AS min_mean, min(sim_access) AS min_sim FROM sim_dwellings_access_train;
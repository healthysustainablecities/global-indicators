"""
Open space areas setup.

Prepare Areas of Open Space (AOS) for urban liveability indicators using
OpenStreetMap data, with optional supplementation or replacement using a
custom areas_of_interest public_open_space dataset defined in the region
configuration.

Also prepares a blue space layer -- rivers, canals, drains, lakes, wetlands,
beaches and coast -- which is derived directly from the OpenStreetMap import
rather than from the areas of open space, and is measured separately from them.
See blue_space_setup for why the two cannot be the same thing.
"""

import sys
import time

# Set up project and region parameters for GHSCIC analyses
import ghsci
from script_running_log import script_running_log
from sqlalchemy import inspect, text


def add_required_osm_tags(r, oss):
    """Define tags for which presence of values is suggestive of some kind of open space, given configuration parameter ('required tags')."""
    for shape in ['line', 'point', 'polygon', 'roads']:
        required_tags = '\n'.join(
            [
                (
                    f"""ALTER TABLE {r.config['osm_prefix']}_{shape} ADD COLUMN IF NOT EXISTS "{x}" varchar;"""
                )
                for x in oss['os_required']['criteria']
            ],
        )
        sql = f"""
        -- Add other columns which are important if they exists, but not important if they don't
        -- --- except that their presence is required for ease of accurate querying.
        {required_tags}"""
        with r.engine.begin() as connection:
            connection.execute(text(required_tags))


def aos_setup_queries(r, oss):
    """A set of queries used to set up a dataset of open space areas using OpenStreetMap data, given a set of configuration definitions."""
    if 'aos_public_large_nodes_30m_line' in r.tables:
        print(
            'Areas of Open Space (AOS) for urban liveability indicators has previously been prepared for this region.\n',
        )
    else:
        aos_setup_queries = [
            f"""
-- Create a 'Not Open Space' table
-- DROP TABLE IF EXISTS not_open_space;
CREATE TABLE IF NOT EXISTS not_open_space AS
SELECT ST_Union(geom) AS geom FROM {r.config['osm_prefix']}_polygon p
WHERE {oss['exclusion_criteria']};
""",
            f"""
-- Create an 'Open Space' table
-- DROP TABLE IF EXISTS open_space;
CREATE TABLE IF NOT EXISTS open_space AS
SELECT p.* FROM {r.config['osm_prefix']}_polygon p
WHERE ({oss['os_inclusion']['criteria']}
    OR p.landuse IN ({oss['os_landuse']['criteria']})
    OR p.boundary IN ({oss['os_boundary']['criteria']}));
""",
            """
-- Create unique POS id and add indices
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS os_id SERIAL PRIMARY KEY;
CREATE INDEX IF NOT EXISTS open_space_idx ON open_space USING GIST (geom);
CREATE INDEX IF NOT EXISTS not_open_space_idx ON not_open_space USING GIST (geom);
""",
            """
-- Remove any portions of open space geometry intersecting excluded regions
UPDATE open_space p
SET geom = ST_Difference(p.geom,x.geom)
FROM not_open_space x
WHERE ST_Intersects(p.geom,x.geom);
-- Drop any empty geometries (ie. those which were wholly covered by excluded regions)
DELETE FROM open_space WHERE ST_IsEmpty(geom);
""",
            """
-- Create variable for park size
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS area_ha double precision;
UPDATE open_space SET area_ha = ST_Area(geom)/10000.0;
""",
            f"""
-- Create variable for associated line tags
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS tags_line jsonb;
WITH tags AS (
SELECT o.os_id,
    jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.waterway) d)))AS attributes
FROM {r.config['osm_prefix']}_line  l,open_space o"""
            + """
WHERE ST_Intersects (l.geom,o.geom) )
UPDATE open_space o SET tags_line = attributes
FROM (SELECT os_id,
            jsonb_agg(distinct(attributes)) AS attributes
    FROM tags
    WHERE attributes != '{}'::jsonb
    GROUP BY os_id) t
WHERE o.os_id = t.os_id
AND t.attributes IS NOT NULL
;
""",
            f"""
-- Create variable for associated point tags
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS tags_point jsonb;
WITH tags AS (
SELECT o.os_id,
    jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT l.amenity,l.leisure,l."natural",l.tourism,l.historic) d)))AS attributes
FROM {r.config['osm_prefix']}_point l,open_space o"""
            + """
WHERE ST_Intersects (l.geom,o.geom) )
UPDATE open_space o SET tags_point = attributes
FROM (SELECT os_id,
            jsonb_agg(distinct(attributes)) AS attributes
    FROM tags
    WHERE attributes != '{}'::jsonb
    GROUP BY os_id) t
WHERE o.os_id = t.os_id
AND t.attributes IS NOT NULL
;
""",
            f"""
-- Create water feature indicator
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS water_feature boolean;
UPDATE open_space SET water_feature = FALSE;
UPDATE open_space SET water_feature = TRUE
WHERE "natural" IN ({oss['os_water']['criteria']})
    OR landuse IN ({oss['os_water']['criteria']})
    OR leisure IN ({oss['os_water']['criteria']})
    OR sport IN ({oss['os_water_sports']['criteria']})
    OR beach IS NOT NULL
    OR river IS NOT NULL
    OR water IS NOT NULL
    OR waterway IS NOT NULL
    OR wetland IS NOT NULL;
""",
            f"""
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS linear_features boolean;
UPDATE open_space SET linear_features = TRUE
WHERE waterway IN ({oss['os_linear']['criteria']})
    OR "natural" IN ({oss['os_linear']['criteria']})
    OR landuse IN ({oss['os_linear']['criteria']})
    OR leisure IN ({oss['os_linear']['criteria']}) ;
""",
            """
-- Create variable for AOS water geometry
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS water_geom geometry;
UPDATE open_space SET water_geom = geom WHERE water_feature = TRUE;
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS min_bounding_circle_area double precision;
UPDATE open_space SET min_bounding_circle_area = ST_Area(ST_MinimumBoundingCircle(geom));
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS min_bounding_circle_diameter double precision;
UPDATE open_space SET min_bounding_circle_diameter = 2*sqrt(min_bounding_circle_area / pi());
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS roundness double precision;
UPDATE open_space SET roundness = ST_Area(geom)/(ST_Area(ST_MinimumBoundingCircle(geom)));
""",
            f"""
-- Create indicator for linear features informed through EDA of OS topology
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS linear_feature boolean;
UPDATE open_space SET linear_feature = FALSE;
UPDATE open_space SET linear_feature = TRUE
WHERE {oss['linear_feature_criteria']['criteria']};
""",
            """
---- Create 'Acceptable Linear Feature' indicator
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS acceptable_linear_feature boolean;
UPDATE open_space SET acceptable_linear_feature = FALSE WHERE linear_feature = TRUE;
UPDATE open_space o SET acceptable_linear_feature = TRUE
FROM (SELECT os_id,geom FROM open_space WHERE linear_feature = FALSE) nlf
WHERE o.linear_feature IS TRUE
AND  (
    -- acceptable if within a non-linear feature
    ST_Within(o.geom,nlf.geom)
OR  (
    -- acceptable if it intersects a non-linear feature if it is not too long
    -- and it has some reasonably strong relation with a non-linear feature
    o.min_bounding_circle_diameter < 800
    AND (
        -- a considerable proportion of geometry is within the non-linear feature
        (ST_Intersects(o.geom,nlf.geom)
        AND
        (st_area(st_intersection(o.geom,nlf.geom))/st_area(o.geom)) > .2)
    OR (
        -- acceptable if there is sufficent conjoint distance (> 50m) with a nlf
        ST_Length(ST_CollectionExtract(ST_Intersection(o.geom,nlf.geom), 2)) > 50
        AND o.os_id < nlf.os_id
        AND ST_Touches(o.geom,nlf.geom))))
    );
-- a feature identified as linear is acceptable as an OS if it is
--  large enough to contain an OS of sufficient size (0.4 Ha?)
-- (suggests it may be an odd shaped park with a lake; something like that)
-- Still, if it is really big its acceptability should be constrained
-- hence limit of min bounding circle diameter
UPDATE open_space o SET acceptable_linear_feature = TRUE
FROM open_space alt
WHERE o.linear_feature IS TRUE
AND  o.acceptable_linear_feature IS FALSE
AND o.min_bounding_circle_diameter < 800
AND  o.geom && alt.geom
AND st_area(st_intersection(o.geom,alt.geom))/10000.0 > 0.4
AND o.os_id != alt.os_id;
""",
            f"""
-- Remove potentially identifying tags from records
UPDATE open_space SET tags =  tags - {oss['exclude_tags_like_name']} - ARRAY[{oss['identifying_tags_to_exclude_other_than_name']['criteria']}]
;
""",
            f"""
-- Create variable to indicate public access, default of True
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS public_access boolean;
UPDATE open_space SET public_access = FALSE;
UPDATE open_space SET public_access = TRUE
WHERE {oss['public_space']}
;
""",
            """
-- Check if area is within an indicated public access area
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS within_public boolean;
UPDATE open_space SET within_public = FALSE;
UPDATE open_space o
    SET within_public = TRUE
FROM open_space x
WHERE x.public_access = TRUE
    AND ST_CoveredBy(o.geom,x.geom)
    AND o.os_id!=x.os_id;
""",
            """
-- Check if area is within an indicated not public access area
-- for example, an OS may be within a non-public area nested within a public area
-- this additional check is required to ensure within_public is set to false
UPDATE open_space o
    SET public_access = FALSE
FROM open_space x
WHERE o.public_access = TRUE
    AND x.public_access = FALSE
    AND ST_CoveredBy(o.geom,x.geom)
    AND o.os_id!=x.os_id;
""",
            """
-- If an open space is within or co-extant with a space flagged as not having public access
-- which is not itself covered by a public access area
-- then it too should be flagged as not public (ie. public_access = FALSE)
UPDATE open_space o
    SET public_access = FALSE
FROM open_space x
WHERE o.public_access = TRUE
    AND x.public_access = FALSE
    AND x.within_public = FALSE
    AND ST_CoveredBy(o.geom,x.geom);
""",
            """
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_public geometry;
ALTER TABLE open_space ADD COLUMN IF NOT EXISTS geom_not_public geometry;
UPDATE open_space SET geom_public = geom WHERE public_access = TRUE;
UPDATE open_space SET geom_not_public = geom WHERE public_access = FALSE;
""",
            f"""
-- Create Areas of Open Space (AOS) table
-- the 'geom' attributes is the area within an AOS
--    -- this is what we want to use to evaluate collective OS area within the AOS (aos_ha)

-- DROP TABLE IF EXISTS open_space_areas;
CREATE TABLE IF NOT EXISTS open_space_areas AS
WITH clusters AS(
    SELECT unnest(ST_ClusterWithin(open_space.geom, .001)) AS gc
    FROM open_space
    WHERE (public_access IS TRUE
        OR
        (public_access IS FALSE
            AND
            within_public IS TRUE
            AND (acceptable_linear_feature IS TRUE
                OR
                linear_feature IS FALSE)))
    AND (linear_feature IS FALSE
            OR
            (acceptable_linear_feature IS TRUE
            ))
    AND linear_features IS NULL
UNION
    SELECT unnest(ST_ClusterWithin(not_public_os.geom, .001)) AS gc
    FROM open_space AS not_public_os
    WHERE public_access IS FALSE
    AND within_public IS FALSE
    AND linear_features IS NULL
UNION
    SELECT  linear_os.geom AS gc
    FROM open_space AS linear_os
    WHERE (linear_feature IS TRUE
    AND acceptable_linear_feature IS FALSE
    AND public_access IS TRUE
    AND linear_features IS NULL)
UNION
    SELECT  waterway_os.geom AS gc
    FROM open_space AS waterway_os
    WHERE linear_features IS TRUE
    )
, unclustered AS( --unpacking GeomCollections
    SELECT row_number() OVER () AS cluster_id, (ST_DUMP(gc)).geom AS geom
    FROM clusters)
SELECT cluster_id as aos_id,
    jsonb_agg(jsonb_strip_nulls(to_jsonb((SELECT d FROM (SELECT {oss['os_add_as_tags']['criteria']}) d))
        || hstore_to_jsonb(tags)
        || jsonb_build_object('tags_line',tags_line)
        || jsonb_build_object('tags_point',tags_point))) AS attributes,
    COUNT(1) AS numgeom,
    ST_Union(geom_public) AS geom_public,
    ST_Union(geom_not_public) AS geom_not_public,
    ST_Union(water_geom) AS geom_water,
    ST_Union(geom) AS geom
    FROM open_space
    INNER JOIN unclustered USING(geom)
    GROUP BY cluster_id;
""",
            """
CREATE UNIQUE INDEX IF NOT EXISTS aos_idx ON open_space_areas (aos_id);
CREATE INDEX IF NOT EXISTS idx_aos_jsb ON open_space_areas USING GIN (attributes);
""",
            """
-- Create variable for AOS size
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_public double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_not_public double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha double precision;
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_water double precision;
""",
            """
-- Calculate total area of AOS in Ha
UPDATE open_space_areas SET aos_ha_public = COALESCE(ST_Area(geom_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha_not_public = COALESCE(ST_Area(geom_not_public)/10000.0,0);
UPDATE open_space_areas SET aos_ha = ST_Area(geom)/10000.0;
UPDATE open_space_areas SET aos_ha_water = COALESCE(ST_Area(geom_water)/10000.0,0);
""",
            """
-- Set water_feature as true where OS feature intersects a noted water feature
-- wet by association
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS has_water_feature boolean;
UPDATE open_space_areas SET has_water_feature = FALSE;
UPDATE open_space_areas o SET has_water_feature = TRUE
FROM (SELECT * from open_space WHERE water_feature = TRUE) w
WHERE ST_Intersects (o.geom,w.geom);
""",
            """
-- Create variable for Water percent
ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS water_percent numeric;
UPDATE open_space_areas SET water_percent = 0;
UPDATE open_space_areas SET water_percent = 100 * aos_ha_water/aos_ha::numeric WHERE aos_ha > 0;
""",
        ]
        for sql in aos_setup_queries:
            query_start = time.time()
            print(f'\nExecuting: {sql}')
            with r.engine.begin() as connection:
                connection.execute(text(sql))
            print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')


def blue_space_criteria(oss):
    """The WHERE clauses selecting blue space polygons and lines.

    An excluded feature is dropped whichever source it came from.  The exclusion
    is wrapped in COALESCE because an SQL comparison against a NULL tag yields
    NULL rather than false, which would otherwise silently discard every feature
    that simply has no value for the tag being excluded on.
    """
    excluded = oss['blue_space_excluded']['criteria']
    keep = f'NOT COALESCE({excluded}, FALSE)'
    return (
        f"({oss['blue_space_polygon']['criteria']}) AND {keep}",
        f"({oss['blue_space_line']['criteria']}) AND {keep}",
    )


def blue_space_setup(r, oss):
    """Identify blue space: water features residents may reach and make use of.

    Derived directly from the OpenStreetMap import rather than from open_space,
    because two rules in the open space pipeline would otherwise hide exactly
    what this measures, and both of those rules are right where they are:

    1. Water is deliberately not public open space.  ``additional_public_criteria``
       requires ``water_feature = FALSE``, so a lake or canal contributes to
       ``aos_ha_not_public`` and never to ``aos_ha_public``.
    2. Linear water is held out of the areas of open space clustering
       (``linear_features``).  Without that, a river or canal touching several
       parks would chain them into one enormous area whose exterior ring, which
       is where access is measured from, would grant 'access to a large public
       open space' along its entire length.

    Linear water is included here as line geometry rather than only as polygons.
    Canals and drains are commonly mapped in OpenStreetMap as ways and never
    appear in the polygon table the open space pipeline is built from, so a
    polygon-only definition cannot see a canal network at all -- which in an arid
    city is most of the blue space there is.

    No public access test, no linear feature test and no clustering are applied:
    a continuous river or canal corridor is the real feature here, not an
    artefact of contiguity.  Because length is not area, polygon areas are
    recorded and linear features are left without one, and no size or per capita
    claim is made of the layer.
    """
    polygon_criteria, line_criteria = blue_space_criteria(oss)
    minimum = oss['blue_space_min_area_ha']['criteria'] or 0
    srid = r.config['crs']['srid']
    queries = [
        f"""
DROP TABLE IF EXISTS blue_space;
CREATE TABLE blue_space AS
SELECT row_number() OVER () AS blue_id, blue_type, source, area_ha, geom
FROM (
    SELECT 'polygon'::text AS blue_type,
           'OpenStreetMap'::text AS source,
           ST_Area(geom)/10000.0 AS area_ha,
           geom
      FROM {r.config['osm_prefix']}_polygon
     WHERE {polygon_criteria}
    UNION ALL
    SELECT 'line'::text AS blue_type,
           'OpenStreetMap'::text AS source,
           NULL::double precision AS area_ha,
           geom
      FROM {r.config['osm_prefix']}_line
     WHERE {line_criteria}
) w
-- a minimum size applies to water bodies only; a canal has no meaningful area
WHERE blue_type = 'line' OR area_ha >= {minimum};
CREATE INDEX blue_space_gix ON blue_space USING GIST (geom);
""",
    ]
    for sql in queries:
        query_start = time.time()
        print(f'\nExecuting: {sql}')
        with r.engine.begin() as connection:
            connection.execute(text(sql))
        print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')
    entries = ghsci.custom_data_entries(
        (r.config.get('areas_of_interest') or {}).get('blue_space'),
    )
    if entries:
        append_custom_blue_space(r, entries)
    blue_space_nodes_setup_query(r, srid)
    attribute_open_space_with_blue_space(r)


def append_custom_blue_space(r, entries):
    """Append configured custom blue space data to the OpenStreetMap-derived layer.

    For cities whose water network is mapped by a local authority rather than in
    OpenStreetMap.  Loaded through the same path as custom open space, then
    appended with new blue_id values so re-runs remain idempotent.
    """
    print('Supplementing blue space using provided data...')
    try:
        load_custom_open_space(r, entries, layer='custom_blue_space')
        sql = """
        -- Remove any custom features appended by a previous run
        ALTER TABLE blue_space ADD COLUMN IF NOT EXISTS custom_blue boolean;
        DELETE FROM blue_space WHERE custom_blue IS TRUE;
        INSERT INTO blue_space (blue_id, blue_type, source, area_ha, geom, custom_blue)
        SELECT (SELECT COALESCE(MAX(blue_id), 0) FROM blue_space)
                   + row_number() OVER (),
               CASE WHEN ST_Dimension(geom) = 2 THEN 'polygon' ELSE 'line' END,
               'custom',
               CASE WHEN ST_Dimension(geom) = 2
                    THEN ST_Area(geom)/10000.0 END,
               geom,
               TRUE
          FROM custom_blue_space;
        """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    except Exception as e:
        raise Exception(
            f'Error loading the custom blue space data configured for this region: {e}\n\nPlease check the areas_of_interest blue_space configuration; in particular, that the data path is correct, that any layer or query syntax is valid, and that the data has a defined coordinate reference system and overlaps the study region.',
        ) from e


def blue_space_nodes_setup_query(r, srid):
    """Points along blue space edges, retained where a street passes within 30 m.

    Mirrors the aos_line / aos_nodes / aos_public_*_nodes_30m_line chain used for
    open space, so that walking access to a canal bank or a lake shore is
    measured exactly as access to any other destination is.  Polygons are sampled
    along their exterior ring and linear features along their length; an
    unbounded linear feature is a problem for area, not for proximity, and the
    question this feeds is how far away the nearest water is.
    """
    queries = [
        f"""
    -- Reduce blue space to the lines access can be measured to
    DROP TABLE IF EXISTS blue_space_line;
    CREATE TABLE blue_space_line AS
    WITH bounds AS (
        SELECT blue_id,
               ST_SetSRID(st_astext((ST_Dump(geom)).geom), {srid}) AS geom
          FROM blue_space
    )
    SELECT blue_id, ST_Length(geom)::numeric AS length, geom
      FROM (
        SELECT blue_id,
               CASE WHEN ST_Dimension(geom) = 2
                    THEN ST_ExteriorRing(geom)
                    ELSE geom END AS geom
          FROM bounds
      ) t
     WHERE geom IS NOT NULL AND ST_Length(geom) > 0;
    """,
        """
    -- Generate a point every 20 m along blue space edges
    DROP TABLE IF EXISTS blue_space_nodes;
    CREATE TABLE blue_space_nodes AS
    WITH b AS (
        SELECT blue_id,
               length,
               generate_series(0, 1, (20/length)) AS fraction,
               geom
          FROM blue_space_line
    )
    SELECT blue_id,
           row_number() over(PARTITION BY blue_id) AS node,
           ST_LineInterpolatePoint(geom, fraction) AS geom
      FROM b;
    CREATE INDEX blue_space_nodes_gix ON blue_space_nodes USING GIST (geom);
    """,
        """
    -- Retain the points a street passes within 30 m of; distinct, so a point
    -- near several streets is not repeated
    DROP TABLE IF EXISTS blue_space_nodes_30m_line;
    CREATE TABLE blue_space_nodes_30m_line AS
    SELECT DISTINCT n.*
      FROM blue_space_nodes n, edges l
     WHERE ST_DWithin(n.geom, l.geom, 30);
    CREATE INDEX blue_space_nodes_30m_line_gix
        ON blue_space_nodes_30m_line USING GIST (geom);
    """,
    ]
    for sql in queries:
        query_start = time.time()
        print(f'\nExecuting: {sql}')
        with r.engine.begin() as connection:
            connection.execute(text(sql))
        print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')


def attribute_open_space_with_blue_space(r):
    """Record each area of open space's relationship to the blue space layer.

    ``aos_blue_distance_m`` is the distance to the nearest blue space, recorded
    as a distance rather than as a flag against some threshold so that any
    threshold can be applied afterwards without re-running the analysis.  This is
    how a park beside a canal is identified: ``aos_ha_water`` counts only water
    clustered into the area of open space itself, which by design excludes the
    linear water running alongside it.

    Water attributes are also filled in for any area of open space that has none
    -- those supplied as custom data rather than derived from OpenStreetMap,
    whether supplementing or replacing it.  They were previously set to zero,
    which reported every such area as containing no water whether or not it did,
    and so silently emptied any indicator built on ``aos_ha_water``.  Areas
    already attributed from OpenStreetMap are left alone.
    """
    sql = """
    ALTER TABLE open_space_areas
        ADD COLUMN IF NOT EXISTS aos_ha double precision;
    ALTER TABLE open_space_areas
        ADD COLUMN IF NOT EXISTS aos_ha_water double precision;
    ALTER TABLE open_space_areas
        ADD COLUMN IF NOT EXISTS has_water_feature boolean;
    ALTER TABLE open_space_areas
        ADD COLUMN IF NOT EXISTS water_percent numeric;
    ALTER TABLE open_space_areas
        ADD COLUMN IF NOT EXISTS aos_blue_distance_m double precision;
    UPDATE open_space_areas
       SET aos_ha = ST_Area(geom)/10000.0
     WHERE aos_ha IS NULL;
    UPDATE open_space_areas o
       SET aos_blue_distance_m = (
            SELECT ST_Distance(o.geom, b.geom)
              FROM blue_space b
             ORDER BY o.geom <-> b.geom
             LIMIT 1
       );
    -- Water area is measured against the blue space polygons; linear water has
    -- no area to contribute, but still counts as a water feature present.
    UPDATE open_space_areas o
       SET aos_ha_water = COALESCE((
            SELECT SUM(ST_Area(ST_Intersection(o.geom, b.geom)))/10000.0
              FROM blue_space b
             WHERE b.blue_type = 'polygon' AND ST_Intersects(o.geom, b.geom)
       ), 0),
           has_water_feature = EXISTS (
            SELECT 1 FROM blue_space b WHERE ST_Intersects(o.geom, b.geom)
       )
     WHERE o.aos_ha_water IS NULL;
    UPDATE open_space_areas
       SET water_percent = CASE WHEN aos_ha > 0
                                THEN 100 * aos_ha_water/aos_ha::numeric
                                ELSE 0 END
     WHERE water_percent IS NULL;
    """
    query_start = time.time()
    print(f'\nExecuting: {sql}')
    with r.engine.begin() as connection:
        connection.execute(text(sql))
    print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')


# Public open space node layer definitions: {name -> SQL criteria on aos_public,
# or None for no further restriction}.  'any' and 'large' are the globally
# comparable pair the standard indicators are built on and should not be
# redefined lightly.  'water' identifies public open space that contains mapped
# water -- a park with a lake -- which is a different question from access to
# blue space itself (the blue_space layer), and is reported alongside it rather
# than instead of it.
PUBLIC_OPEN_SPACE_VARIANTS = {
    'any': None,
    'large': 'a.aos_ha_public > 1.5',
    'water': 'a.aos_ha_water > 0',
}


def public_open_space_variants(config):
    """Resolve the public open space node layers to derive for a region.

    Takes the region configuration mapping rather than the region, so that the
    resolution can be exercised without a database, as the other configuration
    resolvers (``osm_open_space_config``, ``activity_centre_config``) are.

    A region may add its own variants, or redefine the built-in ones, through
    ``areas_of_interest: public_open_space_variants``.  Each value is an SQL
    condition on the ``aos_public`` alias ``a``; ``aos_blue_distance_m`` is
    available there too, so a region may define, say, water-adjacent open space
    without altering what counts as public open space.
    """
    variants = dict(PUBLIC_OPEN_SPACE_VARIANTS)
    configured = ((config or {}).get('areas_of_interest') or {}).get(
        'public_open_space_variants',
    )
    if isinstance(configured, dict):
        variants.update(configured)
    return variants


def public_open_space_variant_query(name, criteria):
    """SQL deriving one public open space node layer.

    Distinct is used to avoid redundant duplication of points where they are
    within 30 m of multiple roads.
    """
    restriction = f'AND ({criteria})' if criteria else ''
    return f"""
    -- Create table of {name} public open space points within 30m of lines
    -- (should be your road network)
    DROP TABLE IF EXISTS aos_public_{name}_nodes_30m_line;
    CREATE TABLE IF NOT EXISTS aos_public_{name}_nodes_30m_line AS
    SELECT DISTINCT n.*
    FROM aos_nodes n LEFT JOIN aos_public a ON n.aos_id = a.aos_id,
        edges l
    WHERE a.aos_id IS NOT NULL
    {restriction}
    AND ST_DWithin(n.geom, l.geom, 30);
    CREATE INDEX aos_public_{name}_nodes_30m_line_gix
        ON aos_public_{name}_nodes_30m_line USING GIST (geom);
    """


def public_open_space_nodes_setup_query(r):
    public_open_space_nodes_setup_query = (
        [
            f"""
    -- Create a linestring aos table
    DROP TABLE IF EXISTS aos_line;
    CREATE TABLE IF NOT EXISTS aos_line AS
    WITH bounds AS
    (SELECT aos_id, ST_SetSRID(st_astext((ST_Dump(geom)).geom),{r.config['crs']['srid']}) AS geom  FROM open_space_areas)
    SELECT aos_id, ST_Length(geom)::numeric AS length, geom
    FROM (SELECT aos_id, ST_ExteriorRing(geom) AS geom FROM bounds) t;
    """,
            """
    -- Generate a point every 20m along a park outlines:
    DROP TABLE IF EXISTS aos_nodes;
    CREATE TABLE IF NOT EXISTS aos_nodes AS
    WITH aos AS
    (SELECT aos_id,
            length,
            generate_series(0,1,20/length) AS fraction,
            geom FROM aos_line)
    SELECT aos_id,
        row_number() over(PARTITION BY aos_id) AS node,
        ST_LineInterpolatePoint(geom, fraction)  AS geom
    FROM aos;

    CREATE INDEX aos_nodes_idx ON aos_nodes USING GIST (geom);
    ALTER TABLE aos_nodes ADD COLUMN IF NOT EXISTS aos_entryid varchar;
    UPDATE aos_nodes SET aos_entryid = aos_id::text || ',' || node::text;
    """,
            """
    -- Create subset data for public_open_space_areas
    DROP TABLE IF EXISTS aos_public;
    CREATE TABLE IF NOT EXISTS aos_public AS
    -- restrict to features > 10 sqm (e.g. 5m x 2m; this is very small, but plausible - and should be excluded)
    SELECT * FROM open_space_areas WHERE aos_ha_public > 0.001;
    CREATE INDEX aos_public_idx ON aos_public (aos_id);
    CREATE INDEX aos_public_gix ON aos_public USING GIST (geom);
    """,
        ]
        + [
            public_open_space_variant_query(name, criteria)
            for name, criteria in public_open_space_variants(r.config).items()
        ]
    )
    for sql in public_open_space_nodes_setup_query:
        query_start = time.time()
        print(f'\nExecuting: {sql}')
        with r.engine.begin() as connection:
            connection.execute(text(sql))
        print(f'Executed in {(time.time() - query_start) / 60:04.2f} mins')


def get_custom_open_space_config(r):
    """Return the list of public open space data entries configured with data (an empty list if none).

    Checks areas_of_interest public_open_space first; a legacy top-level
    public_open_space entry is also supported, implying replace: true.
    """
    areas_of_interest = r.config.get('areas_of_interest')
    if isinstance(areas_of_interest, dict):
        entries = ghsci.custom_data_entries(
            areas_of_interest.get('public_open_space'),
        )
        if entries:
            return entries
    public_open_space = r.config.get('public_open_space')
    if (
        isinstance(public_open_space, dict)
        and public_open_space.get('data') is not None
    ):
        return [{**public_open_space, 'replace': True}]
    return []


def load_custom_open_space(r, entries, layer):
    """Load configured custom public open space data entries to a single database layer, restricted to areas intersecting the buffered urban study region.

    A single configured entry is loaded directly (retaining its attributes);
    multiple entries are each staged then combined with a minimal common
    schema (aos_id, custom_src, geom).
    """
    bbox = r.get_bbox_string()
    staged = []
    for i, entry in enumerate(entries):
        source_layer = layer if len(entries) == 1 else f'{layer}_src_{i}'
        query = (
            f' -spat {bbox} -spat_srs {r.config["crs_srid"]} -lco FID=aos_id'
        )
        data = entry['data']
        if '.gpkg:' in data:
            gpkg = data.split(':')
            data = gpkg[0]
            query = f'{query} {gpkg[1]}'
        # any '-where' suffix within the data string is parsed by ogr_to_db
        r.ogr_to_db(
            source=data,
            layer=source_layer,
            query=query,
            promote_to_multi=True,
        )
        staged.append((source_layer, entry))
    if len(entries) > 1:
        selects = ' UNION ALL '.join(
            "SELECT '{label}'::text AS custom_src, geom FROM {table}".format(
                label=str(entry.get('source', table)).replace("'", "''"),
                table=table,
            )
            for table, entry in staged
        )
        combine = f"""
        DROP TABLE IF EXISTS {layer};
        CREATE TABLE {layer} AS
        SELECT row_number() OVER () AS aos_id, custom_src, geom
          FROM ({selects}) sources;
        """
        drops = '\n'.join(
            f'DROP TABLE IF EXISTS {table};' for table, entry in staged
        )
        with r.engine.begin() as connection:
            connection.execute(text(combine))
            connection.execute(text(drops))
    # ensure valid polygonal geometries, restricted to those intersecting the
    # buffered urban study region
    finalise = f"""
    UPDATE {layer}
       SET geom = ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))
     WHERE NOT ST_IsValid(geom);
    DELETE FROM {layer} o
     WHERE NOT EXISTS (
        SELECT 1 FROM {r.config['buffered_urban_study_region']} b
        WHERE ST_Intersects(o.geom, b.geom)
     );
    """
    with r.engine.begin() as connection:
        connection.execute(text(finalise))


def custom_open_space_setup(r, entries):
    """Replace OpenStreetMap open space with the configured custom data (replace: true)."""
    print(
        'Configuring analysis of open space areas using provided data (replacing OpenStreetMap)...',
    )
    try:
        load_custom_open_space(r, entries, layer='open_space_areas')
        sql = """
        -- Create variables for public open space compatibility with AOS-based indicators
        ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS geom_public geometry;
        UPDATE open_space_areas SET geom_public = geom;
        ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS aos_ha_public double precision;
        UPDATE open_space_areas SET aos_ha_public = ST_Area(geom_public)/10000.0;
        """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    except Exception as e:
        raise Exception(
            f'Error loading the custom open space data configured for this region: {e}\n\nPlease check the public_open_space configuration; in particular, that the data path is correct, that any layer or query syntax is valid, and that the data has a defined coordinate reference system and overlaps the study region.',
        ) from e


def supplement_open_space_setup(r, entries):
    """Append the configured custom data to OpenStreetMap-derived open space areas (replace: false, the default)."""
    print(
        'Supplementing OpenStreetMap open space areas using provided data...',
    )
    try:
        load_custom_open_space(
            r,
            entries,
            layer='custom_open_space_areas',
        )
        sql = """
        -- Remove any custom areas appended by a previous run so re-runs remain idempotent
        ALTER TABLE open_space_areas ADD COLUMN IF NOT EXISTS custom_aos boolean;
        DELETE FROM open_space_areas WHERE custom_aos IS TRUE;
        -- Append custom areas, treated as fully public, with new unique aos_id values
        INSERT INTO open_space_areas (aos_id, numgeom, geom, geom_public, custom_aos)
        SELECT (SELECT COALESCE(MAX(aos_id), 0) FROM open_space_areas)
                 + row_number() OVER (),
               1,
               geom,
               geom,
               TRUE
        FROM custom_open_space_areas;
        -- The water attributes are left null here and filled in against the
        -- blue space layer once it exists (attribute_open_space_with_blue_space).
        -- Zeroing them, as this previously did, would report every custom area
        -- as containing no water whether or not it does, and so silently empty
        -- any indicator built on aos_ha_water.
        UPDATE open_space_areas
           SET aos_ha = ST_Area(geom)/10000.0,
               aos_ha_public = ST_Area(geom_public)/10000.0,
               aos_ha_not_public = 0
         WHERE custom_aos IS TRUE;
        DROP TABLE custom_open_space_areas;
        """
        with r.engine.begin() as connection:
            connection.execute(text(sql))
    except Exception as e:
        raise Exception(
            f'Error appending the custom open space data configured for this region to the OpenStreetMap derived open space areas: {e}\n\nPlease check the public_open_space configuration; in particular, that the data path is correct, that any layer or query syntax is valid, and that the data has a defined coordinate reference system and overlaps the study region.',
        ) from e


def osm_open_space_setup(r):
    print(
        'Configuring analysis of open space areas using OpenStreetMap data...',
    )
    # Region-scoped tag definitions: a copy of the global configuration with any
    # region-specific tuning (areas_of_interest: osm_open_space) applied and the
    # derived criteria resolved, so tuning cannot leak between regions.
    oss = ghsci.osm_open_space_config(r.config)
    add_required_osm_tags(r, oss)
    aos_setup_queries(r, oss)


def open_space_areas_setup(codename):
    # simple timer for log file
    start = time.time()
    script = '_06_open_space_areas_setup'
    task = 'Prepare Areas of Open Space (AOS)'
    r = ghsci.Region(codename)
    entries = get_custom_open_space_config(r)
    replace = ghsci.custom_data_replace(
        entries,
        context='areas_of_interest/public_open_space',
    )
    if entries and replace:
        custom_open_space_setup(r, entries)
        # Confirm features were imported; an empty result would otherwise be
        # carried through to the indicators as an absence of open space.
        with r.engine.begin() as connection:
            open_space_count = connection.execute(
                text('SELECT count(*) FROM open_space_areas;'),
            ).scalar()
        if open_space_count == 0:
            raise Exception(
                'The custom open space data configured for this region was loaded, but no features were retrieved.  Please check that the configured public_open_space data overlaps the study region, and that any configured query matches the intended features.',
            )
    else:
        osm_open_space_setup(r)
        if entries:
            supplement_open_space_setup(r, entries)
    # Blue space is derived from the OpenStreetMap import regardless of which
    # source supplied the open space areas, so the tag columns it queries have
    # to exist even where the OpenStreetMap open space path was not taken.
    oss = ghsci.osm_open_space_config(r.config)
    add_required_osm_tags(r, oss)
    blue_space_setup(r, oss)
    public_open_space_nodes_setup_query(r)
    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    open_space_areas_setup(codename)


if __name__ == '__main__':
    main()

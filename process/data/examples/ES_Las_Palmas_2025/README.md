# Las Palmas de Gran Canaria — GHSCI worked example

This folder is the worked example distributed with the Global Healthy and
Sustainable City Indicators (GHSCI) software. It contains everything needed to
run a complete analysis for one city: the region configuration, every input
dataset, and the script that derived those datasets from their original
sources.

It supersedes `example_ES_Las_Palmas_2023`, which targeted 2023 and kept its
configuration and data in separate folders across the repository.

## Running it

Inside the GHSCI container:

```python
import ghsci
r = ghsci.example()
r.analysis()
r.generate()
```

`ghsci.example()` loads this region. Equivalent ways to load it:

```python
r = ghsci.Region('ES_Las_Palmas_2025')
r = ghsci.Region('data/examples/ES_Las_Palmas_2025')   # by path
r = ghsci.example('ee')                                # Earth Engine variant
```

Or from the command line:

```bash
analysis ES_Las_Palmas_2025
```

Outputs are written to
`process/data/_study_region_outputs/ES_Las_Palmas_2025/`.

## What is here

| Folder | Contents |
|---|---|
| `configuration/` | The region configuration, and its Earth Engine variant |
| `boundaries/` | Municipal boundary; secondary school catchments |
| `population/ghsl_100m/` | GHS-POP 2025, 100 m, clipped |
| `openstreetmap/` | OpenStreetMap extract clipped to the buffered boundary |
| `urban_region/` | GHS-UCDB R2024A record for this urban centre |
| `gtfs/` | Guaguas bus schedule |
| `policy/` | Completed policy indicator checklist |
| `images/` | Placeholder report cover images |
| `scripts/` | The script that derived every dataset above |

Around 8 MB in total.

A guided walkthrough of the whole workflow is in `process/example.ipynb`, which
opens in Jupyter Lab via the `lab` command inside the container.

## Configuration is co-located with the data

The configuration lives in `configuration/` in this folder rather than in
`process/configuration/regions/`. GHSCI discovers configuration files in both
places, so `ES_Las_Palmas_2025` works as a codename either way.

Keeping them together makes the folder self-describing: it can be copied,
archived or shared as a complete record of a study region, and every data path
in the configuration is relative to `process/data`, so the whole folder moves
as a unit. This is the recommended pattern for new study regions.

## Regenerating the data

Every excerpt here is reproducible:

```bash
python scripts/prepare_example_data.py
```

Individual steps can be selected:

```bash
python scripts/prepare_example_data.py --steps population gtfs
```

The script downloads the GHS-POP tile and the current Guaguas feed, clips the
OpenStreetMap extract, cuts the urban centre record from the Urban Centre
Database, and copies the boundaries, policy checklist and images.

Two things to know before re-running it:

- The OpenStreetMap step needs the full Canary Islands extract present in this
  folder as `canary-islands-*.osm.pbf`. It is gitignored because it is 59 MB;
  the script prints the URL to download it from.
- The GTFS step re-downloads the **current** feed, which will not be the
  snapshot analysed here. It reports whether any service exceptions fall inside
  the configured analysis window; if any do, review the window before relying
  on the results.

## A caution on the data

This is a demonstration, not an authoritative account of Las Palmas de Gran
Canaria:

- The policy checklist is illustrative and partially completed.
- The cover images are generic placeholders, not photographs of the city.
- Reports generated from this configuration are watermarked as examples, via
  the `example: true` setting in the configuration.

## Licences

Each dataset keeps the licence of its source, and several require attribution.
The OpenStreetMap extract is under the share-alike ODbL, which also covers
analysis outputs derived from it. See [DATA_LICENCES.md](DATA_LICENCES.md) for
per-dataset detail, and [LICENCE.md](LICENCE.md) for the code and
configuration.

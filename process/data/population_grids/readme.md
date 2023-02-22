# Population grid data

Population grid data are used to represent the population distribution within regions of interest.

We recommend usage and configuration of the [R2022a](https://ghsl.jrc.ec.europa.eu/download.php?ds=pop) or more recent population data from the Global Human Settlements Layer project, with a time point of 2020 (or as otherwise appropriate for your project needs, and bearing in mind the limitations of the GHSL population model) and using Mollweide (equal areas, 100m) projection.

Data should be stored in a sub-folder with a descriptive name.  The folder should contain a subset of tiles from GHSL (or in principle, an national grid would work too; this hasn't been trialled).  Example of the sub-folder name include, "GHS_STAT_UCDB2015MT_GLOBE_R2019A", "GHS_POP_E2020_GLOBE_R2022A_54009_100_V1_0", or "GHS_POP_E2020_GLOBE_R2022A_54009_100_V1_0_R14_C12_Chile_Santiago".  The latter would be an example of a folder that contains a single .tif image corresponding to the metropolitan region of Santiago in Chile.

A whole-of-planet population dataset for 2020 can be downloaded from the following link:
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2022A/GHS_POP_E2020_GLOBE_R2022A_54009_100/V1-0/GHS_POP_E2020_GLOBE_R2022A_54009_100_V1_0.zip

This file is approximately 5 GB in size, so if you are only analysing one or a few cities, it may be worth identifying the specific tiles  that relate to these using the interactive map downloader provided by GHSL and storing them as suggested above.

The report describing this data is located [here](https://ghsl.jrc.ec.europa.eu/documents/GHSL_Data_Package_2022.pdf?t=1655995832).

The citation for the data is:
Schiavina M., Freire S., MacManus K. (2022):
GHS-POP R2022A - GHS population grid multitemporal (1975-2030).European Commission, Joint Research Centre (JRC). https://doi.org/10.2905/D6D86A90-4351-4508-99C1-CB074B022C4A

Metadata for the stored population data should be recorded in datasets.yml.

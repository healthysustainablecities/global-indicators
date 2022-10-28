# Global Healthy and Sustainable Cities Indicators Collaboration spatial urban indicators framework (global-indicators)

An open-source tool for calculating spatial indicators for healthy, sustainable cities worldwide using open or custom data.

This software framework provides a generalized method to measure spatial urban indicators for within- and between-city comparisons with outputs as spatial point data as well as high resolution small area and overall city summaries. The methodology and the open data approach developed in this research can be expanded to many cities worldwide to support benchmarking, analysis and monitoring of local policies, track progress, and inform interventions towards achieving healthy, equitable and sustainable cities.

The default core set of spatial urban indicators calculated includes:

- Urban area in square kilometers
- Population density (persons per square kilometre)
- Street connectivity (intersections per square kilometer)
- Access to destinations within 500 meters:  
    - a supermarket
    - a convenience store
    - a public transport stop (any; or optionally, regularly serviced)
    - a public open space (e.g. park or square; any, or larger than 1.5 hectares)
- A score for access to a range of daily living amenities
- A walkability index

# How to set up and get started?

Detailed directions to set up and perform the 3-step process to calculate spatial indicators of urban design and transport features for healthy and sustainable cities, with data outputs in both geopackage (for mapping) and CSV (without geometry fields, for non-spatial analysis) formats are provided in the [process](./process) folder.

The resulting city-specific datasets of spatial indicators of urban design and transport features, calculated at a range of scales from address points, to high resolution grids of the spatial distribution, to overall city summaries can be used to provide evidence to support policy makers and planners to target interventions within cities, compare performance across cities, and when measured across time can be used to monitor progress for achieving urban design goals for reducing inequities. Moreover, they provide a rich source of data for those advocating for disadvantaged and vulnerable community populations, to provide evidence for whether urban policies for where they live are serving their needs.

Our repository [global_scorecards](https://github.com/global-healthy-liveable-cities/global_scorecards) provides a framework for reporting on policy and spatial indicators in multiple languages that we developed for creating accessible reports for disseminating findings of our 25-city study (see https://healthysustainablecities.org). We plan to further update the reporting to work more generally with our ambitions for the [1000 city challenge](https://www.healthysustainablecities.org/1000cities).  

# Citation

Liu S, Higgs C, Arundel J, Boeing G, Cerdera N, Moctezuma D, Cerin E, Adlakha D, Lowe M, Giles-Corti B (2022) A Generalized Framework for Measuring Pedestrian Accessibility around the World Using Open Data. Geographical Analysis. 54(3):559-582. https://doi.org/10.1111/gean.12290 

The tool was designed to be used for a 25-city comparative analysis, published as:

Boeing G, Higgs C, Liu S, Giles-Corti B, Sallis JF, Cerin E, et al. (2022) Using open data and open-source software to develop spatial indicators of urban design and transport features for achieving healthy and sustainable cities. The Lancet Global Health. 10(6):e907–18. https://doi.org/10.1016/S2214-109X(22)00072-9 

# How to contribute

#### If you've found an issue or want to request a new feature:

  - check the [issues](https://github.com/global-healthy-liveable-cities/global-indicators/issues) first
  - open an new issue in the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues) filling out all sections of the template, including a minimal working example or screenshots so others can independently and completely reproduce the problem
  
#### If you want to contribute to a feature:

  - post your proposal on the [issue tracker](https://github.com/global-healthy-liveable-cities/global-indicators/issues)
  - fork the repo, make your change (adhering to existing coding, commenting, and docstring styles)
  - Create your feature branch: `git checkout -b my-new-feature`
  - Commit your changes: `git commit -am 'Add some feature'`
  - Push to the branch: `git push origin my-new-feature`
  - Submit a pull request.

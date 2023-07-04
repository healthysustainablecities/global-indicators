"""
Tests for the Global Healthy and Sustainable City Indicator software workflow.

This module may be run from the process directory as follows:

    python -m unittest -v tests/tests.py

For example, from within process directory:

>docker compose -f .test-compose.yml run ghsci
test_global_indicators_shell (tests.tests.tests)
Unix shell script should only have unix-style line endings. ... ok
test_project_setup (tests.tests.tests)
Check if _project_setup.py imported successfully. ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.003s

OK

Successful running of all tests may require running of tests within the global-indicators Docker container, hence the use of a custom .test-compose.yml for this purpose.
"""

import sys
import unittest

try:
    from subprocesses import ghsci

    project_setup = True
except ImportError as e:
    project_setup = f'ghsci.py import error: {e}'


class tests(unittest.TestCase):
    """A collection of tests to help ensure functionality."""

    def test_global_indicators_shell(self):
        """Unix shell script should only have unix-style line endings."""
        counts = calculate_line_endings('../global-indicators.sh')
        lf = counts.pop(b'\n')
        self.assertTrue(sum(counts.values()) == 0 and lf > 0)

    def test_project_setup(self):
        """Check if _project_setup.py imported successfully."""
        self.assertTrue(project_setup)

    def test_load_example_region(self):
        """Load example region."""
        codename = 'example_ES_Las_Palmas_2023'
        r = ghsci.Region(codename)

    def test_example_analysis(self):
        """Analyse example region."""
        codename = 'example_ES_Las_Palmas_2023'
        r = ghsci.Region(codename)
        r._create_database()
        r._create_study_region()
        r._create_osm_resources()
        r._create_network_resources()
        r._create_population_grid()
        r._create_destinations()
        r._create_open_space_areas()
        r._create_neighbourhoods()
        r._create_destination_summary_tables()
        r._link_urban_covariates()
        r._gtfs_analysis()
        r._neighbourhood_analysis()
        r._area_analysis()

    def test_example_generate(self):
        """Generate resources for example region."""
        codename = 'example_ES_Las_Palmas_2023'
        r = ghsci.Region(codename)
        r.generate()

    def test_sensitivity(self):
        """Test sensitivity analysis of urban intersection parameter."""
        reference = 'example_ES_Las_Palmas_2023'
        comparison = 'ES_Las_Palmas_2023_test_not_urbanx'
        # create modified version of reference configuration
        with open(f'./configuration/regions/{reference}.yml') as file:
            configuration = file.read()
            configuration = configuration.replace(
                'ghsl_urban_intersection: true',
                'ghsl_urban_intersection: false',
            )
        with open(f'./configuration/regions/{comparison}.yml', 'w') as file:
            file.write(configuration)
        r = ghsci.Region(comparison)
        r.analysis()
        r.generate()
        r.compare(reference)


def calculate_line_endings(path):
    """
    Tally line endings of different types, returning dictionary of counts.

    Based on code posted at https://stackoverflow.com/questions/29695861/get-newline-stats-for-a-text-file-in-python.
    """
    # order matters!
    endings = [
        b'\r\n',
        b'\n\r',
        b'\n',
        b'\r',
    ]
    counts = dict.fromkeys(endings, 0)

    with open(path, 'rb') as fp:
        for line in fp:
            for x in endings:
                if line.endswith(x):
                    counts[x] += 1
                    break
    return counts


def suite():
    suite = unittest.TestSuite()
    for t in [
        'test_global_indicators_shell',
        'test_project_setup',
        'test_load_example_region',
        'test_example_analysis',
        'test_example_generate',
        'test_sensitivity',
    ]:
        suite.addTest(tests(t))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

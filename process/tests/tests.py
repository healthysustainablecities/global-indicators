"""
Tests for the Global Healthy and Sustainable City Indicator software workflow.

This module may be run from the process directory as follows:

    python -m unittest -v tests/tests.py

For example:

    ghsci@docker-desktop:~/work/process$ python -m unittest -v tests/tests.py
    test_global_indicators_shell (tests.tests.tests)
    Unix shell script should only have unix-style line endings. ... ok

    ----------------------------------------------------------------------
    Ran 1 test in 0.002s

    OK

However, successful running of all tests may require running of tests within the global-indicators Docker container.
"""

import sys
import unittest


def calculate_line_endings(path):
    """
    Tally line endings of different types, returning dictionary of counts.

    Based on code posted at https://stackoverflow.com/questions/29695861/get-newline-stats-for-a-text-file-in-python.
    """
    # order matters!
    endings = [
        b"\r\n",
        b"\n\r",
        b"\n",
        b"\r",
    ]
    counts = dict.fromkeys(endings, 0)

    with open(path, "rb") as fp:
        for line in fp:
            for x in endings:
                if line.endswith(x):
                    counts[x] += 1
                    break
    return counts


class tests(unittest.TestCase):
    """A collection of tests to help ensure functionality."""

    def test_global_indicators_shell(self):
        """Unix shell script should only have unix-style line endings."""
        counts = calculate_line_endings("../global-indicators.sh")
        lf = counts.pop(b"\n")
        self.assertTrue(sum(counts.values()) == 0 and lf > 0)


if __name__ == "__main__":
    unittest.main()

#!/bin/sh -l

/bin/bash -c sleep 3
python -m unittest -v ./tests/tests.py

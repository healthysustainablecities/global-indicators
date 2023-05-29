#!/bin/sh -l

echo "Test example analysis"
time=$(date)
python analysis.py example_ES_Las_Palmas_2023
echo "time=$time" >> $GITHUB_OUTPUT

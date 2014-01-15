#!/bin/bash
cd data/`ls -ltr data/ | tr -s " " |  cut -d " " -f 9 | tail -n 1`
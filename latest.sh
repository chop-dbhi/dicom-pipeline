#!/bin/bash
echo data/`ls -ltr data/ | cut -d " " -f 13 | tail -n 1`

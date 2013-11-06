#!/usr/bin/env python
# Given a date string in 'mm/dd/yyyy' as command argument, this script will descend into the data directory
# and delete the quarantine, no_encounter, from_staging and to_production folders from run directories older or 
# equal to the supplied date. It is used for cleaning out DICOM data files, but leaving the log files from each run.

import dateutil.parser
import datetime
import os
import re
import sys
import shutil

DIRS_TO_DELETE = ['quarantine', 'no_encounter', 'from_staging', 'to_production']

if len(sys.argv) < 2:
    print "Please provide a threshold date in 'mm/dd/yyyy' as argument. Folders as old and older will be cleaned."
    sys.exit()
    
run_dir = re.compile(r'run_at_(\d+)')
threshold_date = dateutil.parser.parse(sys.argv[1])
data_dir = os.path.join(os.getcwd(), 'data')
# Iterate over all directories that match run_at_<secondssinceepoch>

for directory in os.listdir(data_dir):
    match = run_dir.match(directory)
    if match == None:
        continue
    dir_date = datetime.datetime.fromtimestamp(int(match.group(1)))
    if dir_date > threshold_date:
        continue
    for dicom_file_dir in os.listdir(os.path.join(data_dir, directory)):
        if dicom_file_dir in DIRS_TO_DELETE:
            to_delete = os.path.join(data_dir, directory, dicom_file_dir)
            print "Deleting %s" % to_delete
            shutil.rmtree(to_delete)
            

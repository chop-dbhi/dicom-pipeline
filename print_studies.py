# This is a simple utility that prints out all the DICOM Study UIDS 
# found in a directory of DICOM files
import sys
import dicom
import os

studies = set()
for root, dirs, files in os.walk(sys.argv[1]):
     for filename in files:
         ds = dicom.read_file(os.path.join(root,filename))
         study_uid = ds[0x20,0xD].value.strip()
         studies.add(study_uid)

for x in studies:
    print x

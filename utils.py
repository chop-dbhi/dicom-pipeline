# Utility function to count the number of files and unique dicom studies in a directory structure
def dicom_count(directory):
   file_count = 0
   studies = set()

   for root, dirs, files in os.walk(directory):
      for filename in files:
          try:.
              ds = dicom.read_file(os.path.join(root,filename))
          except IOError:
              sys.stderr.write("Unable to read %s" % os.path.join(root, filename))
              continue
          file_count += 1
          study_uid = ds[0x20,0xD].value.strip()
          studies.add(study_uid)
   return (file_count, len(studies))
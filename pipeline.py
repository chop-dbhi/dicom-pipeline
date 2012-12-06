import subprocess
import sys
import time
import os
import re
import dicom
import datetime

from optparse import OptionParser
from ruffus import *
from local_settings import *
from dicom_models.staging.models import *

devnull = None
dicom_store_scp = None
overview = None
run_re = re.compile(r'run_at_(\d+)')
run_dir = os.path.sep.join(['data',"run_at_%d" % int(time.time())])
limit = 0

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-r", "--runlast", default=False, dest="runlast", action="store_true",
            help="Re-run last pipeline.")
    parser.add_option("-m", "--max", default = 0, dest="limit", action="store",
            help="Maximum number of studies to run through pipeline")
    parser.add_option("-p", "--practice", default = False, dest="practice", action="store_true",
            help="Don't modify de-identified studies to include patient aliases, modify the application database, or push to production")
    parser.add_option("-v", "--verbosity", default = 5, dest = "verbosity", action = "store",
            help="Specify pipeline versbosity, 1-10. See Ruffus documentation for details.")
    (options, args) = parser.parse_args()

    try:
        limit = int(options.limit)
    except ValueError:
        print "Max argument must be a number"
        sys.exit()

    if options.runlast:
        if os.path.exists("data"):
            last = 0
            for listing in os.listdir("data"):
                if os.path.isdir(os.path.sep.join(["data",listing])):
                    match = run_re.match(listing)
                    if match:
                        runtime = int(match.group(1))
                        if last < runtime:
                            last = runtime
            if last:
                run_dir = os.path.sep.join(["data", "run_at_%d" % last])

# Utility function to count the number of files and unique dicom studies in a directory structure
def dicom_count(directory):
   file_count = 0
   studies = set()

   for root, dirs, files in os.walk(directory):
      for filename in files:
          try: 
              ds = dicom.read_file(os.path.join(root,filename))
          except IOError:
              continue
          file_count += 1
          study_uid = ds[0x20,0xD].value.strip()
          studies.add(study_uid)
   
   return (file_count, len(studies))

def setup_data_dir():
    global overview 
    if not os.path.exists(run_dir):
        os.makedirs(run_dir)
    print "Working directory will be %s" % run_dir
    overview = open(os.path.sep.join([run_dir, "overview.txt"]), "a")
    now = datetime.datetime.now()
    overview.write("Starting at %s\n" % now.strftime("%Y-%m-%d %H:%M"))

@follows(setup_data_dir)
@files(None, os.path.sep.join([run_dir, "studies_to_retrieve.txt"]))
def get_reviewed_studies(input_file, output_file):
    #TODO Check here for conflicting reviews if more than 1 review is permitted
    studies = RadiologyStudy.objects.filter(radiologystudyreview__has_phi = False,
        radiologystudyreview__exclude = False,  
        radiologystudyreview__relevant = True, 
        radiologystudyreview__has_reconstruction = False,
        radiologystudyreview__image_published = False).distinct()[0:limit-1]
    f = open(output_file, "w")
    for study in studies:
        f.write(study.original_study_uid+"\n")
    f.close()
    overview.write("%d valid reviewed studies.\n" % len(studies))

@follows(get_reviewed_studies, mkdir(os.path.sep.join([run_dir, "from_staging"])))
@files(os.path.sep.join([run_dir, "studies_to_retrieve.txt"]), os.path.sep.join([run_dir, "pull_output.txt"]))
def start_dicom_server(input_file = None, output_file = None):
    global dicom_store_scp
    global devnull
    devnull = open(os.devnull, 'w')
    dicom_store_scp = subprocess.Popen("dcmrcv %s@%s:%d -dest %s" % (LOCAL_AE, LOCAL_HOST, LOCAL_PORT, os.path.sep.join([run_dir, "from_staging"])), 
            stdout=devnull, shell=True)

@files(os.path.sep.join([run_dir, "studies_to_retrieve.txt"]), os.path.sep.join([run_dir, "pull_output.txt"]))
@follows(start_dicom_server)
def request_dicom_files(input_file, output_file = None):
     results = subprocess.check_output("dicom_tools/retrieve.sh %s@%s:%d %s" % (STAGE_AE, 
         STAGE_HOST, STAGE_PORT, input_file), stderr=subprocess.STDOUT, shell=True)
     f = open(os.path.sep.join([run_dir, "pull_output.txt"]), "w")
     f.write(results)
     f.close()
     overview.write("Received %d files containing %d studies\n" % dicom_count(os.path.sep.join([run_dir, "from_staging"])))

@follows(request_dicom_files)
def stop_dicom_server():
    if dicom_store_scp: 
        dicom_store_scp.kill()
        devnull.close()

@files(os.path.sep.join([run_dir, "pull_output.txt"]), os.path.sep.join([run_dir, "anonymize_output.txt"]))
@follows(stop_dicom_server)
def anonymize(input_file = None, output_file = None):
    results = subprocess.check_output("./anonymize.sh %s %s %s %s" % (DICOM_ROOT,
        os.path.sep.join([run_dir, "from_staging"]),
        os.path.sep.join([run_dir, "to_production"]),
        os.path.sep.join([run_dir, "quarantine"])), shell=True)

    f = open(os.path.sep.join([run_dir, "anonymize_output.txt"]), "w")
    f.write(results)
    f.close()

@files(os.path.sep.join([run_dir, "anonymize_output.txt"]), os.path.sep.join([run_dir, "register_output.txt"]))
@follows(anonymize)
def register_with_database(input_file = None, output_file = None):
    additional = ""
    if options.practice:
        additional = " -p"
    results = subprocess.check_output("python loadstudies.py%s -i identity.db -f %s -d %s" % (additional, os.path.sep.join([run_dir,"no_encounter"]), os.path.sep.join([run_dir, "to_production"])),
        stderr=subprocess.STDOUT, shell=True)
    if options.practice:
        f = open(os.path.sep.join([run_dir, "register_output_practice.txt"]), "w")
    else:
        f = open(os.path.sep.join([run_dir, "register_output.txt"]), "w")
    f.write(results)
    f.close()
    overview.write("%d files containing %d studies were successfully hooked up to an encounter.\n" % dicom_count(os.path.sep.join([run_dir, "to_production"])))

@files(os.path.sep.join([run_dir, "register_output.txt"]), os.path.sep.join([run_dir, "push_output.txt"]))
@follows(register_with_database)
def push_to_production(input_file = None, output_file = None):
    results = subprocess.check_output("./push.sh %s %s %d %s" % (PROD_AE, PROD_HOST, PROD_PORT, os.path.sep.join([run_dir, "to_production"])), 
        shell=True)

    f = open(os.path.sep.join([run_dir, "push_output.txt"]), "w")
    f.write(results)
    f.close()
    now = datetime.datetime.now()
    overview.write("Push completed at %s\n" % now.strftime("%Y-%m-%d %H:%M"))

def main():
    pipeline_run([push_to_production], verbose = options.verbosity)
    if overview: 
        overview.close()


if __name__ == "__main__":
    main()

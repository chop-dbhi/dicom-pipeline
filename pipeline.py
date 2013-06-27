import subprocess
import sys
import time
import os
import re
import dicom
import datetime
from optparse import OptionParser
from ruffus import *
from utils import dicom_count
from dicom_anon import dicom_anon

import local_settings as local
from local_settings import *

from django.core.management import setup_environ
setup_environ(local)

from hooks import registry
from dicom_models.staging.models import *

devnull = None
dicom_store_scp = None
overview = None
run_re = re.compile(r'run_at_(\d+)')
run_dir = os.path.sep.join(['data',"run_at_%d" % int(time.time())])
limit = 0
modalities = None

if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-r", "--runlast", default=False, dest="runlast", action="store_true",
            help="Re-run last pipeline.")
    parser.add_option("-m", "--max", default = 10, dest="limit", action="store",
            help="Maximum number of studies to run through pipeline")
    parser.add_option("-p", "--practice", default = False, dest="practice", action="store_true",
            help="Don't modify de-identified studies to include patient aliases, modify the application database, or push to production")
    parser.add_option("-v", "--verbosity", default = 5, dest = "verbosity", action = "store",
            help="Specify pipeline versbosity, 1-10. See Ruffus documentation for details.")
    parser.add_option("-a", "--allowed_modalities", default = "MR,CT", dest = "modalities", action = "store",
            help="Comma separated list of allowed modality types. Defaults to 'MR,CT'")
    parser.add_option("-n", "--no_push", default = False, dest = "no_push", action = "store_true",
            help="Do not push studies to production PACS (stops after registering studies with encounter in database).")
    (options, args) = parser.parse_args()

    try:
        limit = int(options.limit)
    except ValueError:
        print "Max argument must be a number"
        sys.exit()
    modalities = options.modalities

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
        radiologystudyreview__relevant = True,
        radiologystudyreview__has_reconstruction = False,
        exclude = False,
        radiologystudyreview__exclude = False,
        image_published = False).distinct()[0:limit]

    comments = open(os.path.sep.join([run_dir, "comments.txt"]), "w")
    for study in studies:
        comments.write("%s:\n" % study.original_study_uid)
        for review in study.radiologystudyreview_set.all():
            comments.write("\t%s\n" % review.comment)
    comments.close()

    f = open(output_file, "w")
    for study in studies:
        f.write(study.original_study_uid+"\n")
    f.close()
    overview.write("%d valid reviewed studies. Please review comments.txt\n" % len(studies))

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
    results = dicom_anon.driver(os.path.sep.join([run_dir, "from_staging"]),
                                os.path.sep.join([run_dir, "to_production"]),
                                "identity.db",
                                "dicom_limited_vocab.json",
                                os.path.sep.join([run_dir, "quarantine"]),
                                allowed_modalities=modalities,
                                org_root = DICOM_ROOT)

    f = open(os.path.sep.join([run_dir, "anonymize_output.txt"]), "w")
    f.write(results)
    f.close()

@files(os.path.sep.join([run_dir, "anonymize_output.txt"]), os.path.sep.join([run_dir, "missing_protocol_studies.txt"]))
@follows(anonymize)
def check_patient_protocol(input_file = None, output_file = None):
    file_name = os.path.sep.join([run_dir, "studies_to_retrieve.txt"])
    studies_file = open(file_name, "r")
    studies = studies_file.read().splitlines()
    studies_file.close()
 
    protocol_studies = RadiologyStudy.objects.filter(original_study_uid__in=studies,
        radiologystudyreview__has_phi = False,
        radiologystudyreview__relevant = True,
        radiologystudyreview__has_reconstruction = False,
        exclude = False,
        radiologystudyreview__exclude = False,
        radiologystudyreview__has_protocol_series = True).distinct()

    reviewed_protocol_studies = set([x.original_study_uid for x in protocol_studies])

    quarantine_dir = os.path.sep.join([run_dir, "quarantine"])
    found_protocol_studies = set()
    for root, dirs, files in os.walk(quarantine_dir):
        for filename in files:
            try:
                ds = dicom.read_file(os.path.join(root,filename))
            except IOError:
                sys.stderr.write("Unable to read %s" % os.path.join(root, filename))
                continue
            series_desc = ds[0x8,0x103E].value.strip().lower()
            if series_desc == "patient protocol":
                study_uid = ds[0x20,0xD].value.strip()
                found_protocol_studies.add(study_uid)

    marked_but_not_found = reviewed_protocol_studies - found_protocol_studies

    overview.write("%d studies marked as having a protocol series, %d studies found with protocol series during anonymization.\n" % (len(reviewed_protocol_studies), len(found_protocol_studies)))
    overview.write("%d studies marked as having a protocol series but not found, see 'missing_protocol_studies.txt'.\n" % len(marked_but_not_found))

    f = open(os.path.sep.join([run_dir, "reviewed_protocol_studies.txt"]), "w")
    for study in reviewed_protocol_studies:
        f.write(study+"\n")
    f.close()

    f = open(os.path.sep.join([run_dir, "found_protocol_studies.txt"]), "w")
    for study in found_protocol_studies:
        f.write(study+"\n")
    f.close()

    f = open(os.path.sep.join([run_dir, "missing_protocol_studies.txt"]), "w")
    for study in marked_but_not_found:
        f.write(study+"\n")
    f.close()

@files(os.path.sep.join([run_dir, "missing_protocol_studies.txt"]), os.path.sep.join([run_dir, "post_anon_output.txt"]))
@follows(check_patient_protocol)
def post_anon(input_file = None, output_file = None):
    results = registry.get(local.POST_ANON_HOOK)(run_dir, overview, options.practice) 
    if options.practice:
        f = open(os.path.sep.join([run_dir, "post_anon_output_practice.txt"]), "w")
    else:
        f = open(os.path.sep.join([run_dir, "post_anon_output.txt"]), "w")
    f.write(results+"\n")
    f.close()

@files(os.path.sep.join([run_dir, "post_anon_output.txt"]), os.path.sep.join([run_dir, "push_output.txt"]))
@follows(post_anon)
def push_to_production(input_file = None, output_file = None):
    results = subprocess.check_output("./push.sh %s %s %d %s" % (PROD_AE, PROD_HOST, PROD_PORT, os.path.sep.join([run_dir, "to_production"])), 
        shell=True)

    f = open(os.path.sep.join([run_dir, "push_output.txt"]), "w")
    f.write(results)
    f.close()
    now = datetime.datetime.now()
    overview.write("Push completed at %s\n" % now.strftime("%Y-%m-%d %H:%M"))

def main():
    if options.no_push or options.practice:
        pipeline_run([post_anon], verbose = options.verbosity)
    else:
        pipeline_run([push_to_production], verbose = options.verbosity)

    if overview: 
        overview.close()


if __name__ == "__main__":
    main()

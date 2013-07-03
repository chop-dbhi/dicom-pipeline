from django.db.models import Count
from django.conf import settings
from utils import dicom_count
import loader
import subprocess
import os

# run_dir: string of the working directory that the pipeline is using
# overview: stream object used to write notes about this run of the pipeline
# practice: bool determining whether this is a practice run of the pipeline
def associate_to_existing_studies(run_dir, overview, practice):
    additional = ""
    if practice:
        additional = " -p"
    results = subprocess.check_output("python loadstudies.py%s -i identity.db -f %s -d %s" % (additional, os.path.sep.join([run_dir,"no_encounter"]), os.path.sep.join([run_dir, "to_production"])),
        stderr=subprocess.STDOUT, shell=True)
    overview.write("%d files containing %d studies were successfully hooked up to an encounter.\n" % dicom_count(os.path.sep.join([run_dir, "to_production"])))
    return results

def simple_hook(run_dir, overview, practice):
    overview.write("Pass thru hook\n")
    return "Simple pass thru post anon hook"

registry = loader.Registry(default=associate_to_existing_studies, default_name = "default")
registry.register(simple_hook, name = "simple")
loader.autodiscover()

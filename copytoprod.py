import os
import sqlite3
import sys
import logging
import datetime
import shutil
import dicom

from optparse import OptionParser
from django.core.management import setup_environ
import local_settings as local
setup_environ(local)

from django.core.exceptions import ObjectDoesNotExist
from dicom_models.staging.models import RadiologyStudy as RadStudy
from dicom_models.production.models import RadiologyStudy, DataAvailability

s_studies = RadStudy.objects.using('staging').filter(image_published=True)
count = 0
for study in s_studies:
    # Check to see if this study is in production
    study_in_prod = RadiologyStudy.objects.using('production').filter(study_uid=study.study_uid)
    if len(study_in_prod) == 0:
        new_prod_study = RadiologyStudy(study_uid = study.study_uid, modality=study.modality, sop_class=study.sop_class, number_of_series=study.number_of_series, total_images=study.total_images)
    else: 
        new_prod_study = study_in_prod[0]
        new_prod_study.modality = study.modality
        new_prod_study.sop_class = study.sop_class
        new_prod_study.number_of_series = study.number_of_series
        new_prod_study.total_images = study.total_images

    new_prod_study.encounter_id = study.encounter_id
    new_prod_study.patient_id = study.encounter.patient_id
    new_prod_study.save()	

    print "New study %s" % study.study_uid
    count+= 1

print "%d new studies." % count

data = DataAvailability.objects.all()
for d in data:
    d.reset_calculated_fields(save=True)



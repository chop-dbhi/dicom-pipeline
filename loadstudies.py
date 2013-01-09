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

from django.template.loader import get_template
from django.template import Context
from django.db import transaction
from dicom_models.staging.models import (Patient, RadiologyStudy, Encounter)
from django.db import connections
from django.core.exceptions import ObjectDoesNotExist

# The first thing we need to do is scan this directory and gather information about all the dicom files.
# This application assumes that certain fields in all the dicom files have been de-identified, and that
# the information to re-identify them is stored in an sqlite database. Each dicom attribute tag is mapped to a table in te
# dictionary below, and every table has the following columns (id, original, cleaned)

table_map = {
 "0008,0080": "institution",             # Institution name
 "0008,0081": "instaddress",             # Institution Address
 "0008,0090": "physician",               # Referring Physician's name
 "0008,0092": "physaddr",                # Referring Physician's address
 "0008,0094": "physphoner",              # Referring Physician's Phone
 "0008,1048": "physofrecord",            # Physician(s) of Record
 "0008,1049": "physofrecordid",          # Physician(s) of Record Identification
 "0008,1050": "perfphysname",            # Performing Physician's Name
 "0008,1060": "readphysname",            # Reading Physicians Name
 "0008,1070": "operator",                # Operator's Name
 "0008,1010": "station",                 # Station name
 "0010,0010": "patient",                 # Patient's name                              
 "0010,1005": "patientbname",            # Patient's Birth Name
 "0010,0020": "id",                      # Patient's ID
 "0008,0020": "date",                    # Study Date
 "0008,0050": "accession"                # Accession number
}

sop_class = { "1.2.840.10008.5.1.4.1.1.4" : "MR",
              "1.2.840.10008.5.1.4.1.1.2" : "CT",
              "1.2.840.10008.5.1.4.1.1.7" : "SC" }
            
def scan_dicom_files(options):

    logger = logging.getLogger("loadstudies")
    cache = {}
    
    conn = sqlite3.connect(options.db)
    cursor = conn.cursor()
    
    for root, dirs, files in os.walk(options.directory):
        for filename in files:
            try:
                ds = dicom.read_file(os.path.join(root,filename))
            except IOError, e0:
                logger.error("Error reading file %s, it will be moved to %s" % (os.path.join(root,filename), options.faildir ))
                try:
                    shutil.move(os.path.join(root,filename), options.faildir)
                except IOError, e1:
                    logger.error("Error moving file %s" % os.path.join(root,filename))
                    sys.exit()
                continue

            try:
                 study_uid = ds[0x20,0xD].value.strip()
                 series = ds[0x20,0x0E].value.strip()
            except IndexError, ie0:
                logger.error("Error reading file %s. Could not read study or series id. It will be moved to %s" % (os.path.join(root,filename), options.faildir ))
                try:
                    shutil.move(os.path.join(root,filename), options.faildir)
                except IOError, e1:
                    logger.error("Error moving file %s" % os.path.join(root,filename))
                    sys.exit()
                continue

            details = cache.setdefault(study_uid,{'manufactured':False, "series":[], "num_series":0, "num_images":0, "accession":[]})

            # Get the original accesion number
            accession_cleaned = ds[0x8,0x50].value.strip()
            rows = cursor.execute("select original from %s where cleaned=?" % 
                                  table_map["0008,0050"],(accession_cleaned,)).fetchall()
            try:
                accession = rows[0][0]
            except IndexError, e:
                logger.error("Unable to find accession number for %s in identity database. Study in file %s may not be added to the database" % (accession_cleaned, filename))
                continue 
            
            if not accession in details["accession"]:
                  details["accession"].append(accession)
            
            if not series in details["series"]:
                details["series"].append(series)
                details["num_series"] = len(details["series"])
            details["num_images"] += 1

            if not details.has_key("orig_study_uid"):
                rows = cursor.execute("select original from studyuid where cleaned=?",(study_uid,)).fetchall()
                orig_study_uid = None
                try:
                    orig_study_uid = rows[0][0]
                except IndexError, e:
                    logger.error("Unable to find original study id for cleaned study uid %s" % study_uid)
                    conn.close()
                    sys.exit()
                details["orig_study_uid"] = orig_study_uid

            if not details.has_key("file"):
                details["file"] = os.path.join(root,filename)
                
            if not details.has_key("sop_class_uid"):
                details["sop_class_uid"] = ds[0x8,0x16].value.strip()
                try:
                    details["modality"] = sop_class[details["sop_class_uid"]]
                except KeyError,e:
                    logger.error("Unable to determine modality type of sop class %s" % details["sop_class_uid"])
                    sys.exit()
                
            if not details.has_key("patient_alias"):
                cleaned_patient_id = ds[0x10,0x20].value.strip()
                rows = cursor.execute("select original from %s where cleaned=?" % 
                                      table_map["0010,0020"],(cleaned_patient_id,)).fetchall()
                mrn = None
                patient = None
                try:
                    mrn = rows[0][0]
                    patient = Patient.objects.get(patientphi__mrn=mrn)
                except IndexError, e:
                    logger.error("Unable to find MRN for %s in identity database," 
                    " will try to see if this is actually a patient" 
                    " alias already." % cleaned_patient_id)
                    try:
                        patient = Patient.objects.get(alias=cleaned_patient_id)
                    except Patient.DoesNotExist:
                        logger.error("\tUnable to find patient with alias %s, exiting."% cleaned_patient_id)
                        continue
                except Patient.DoesNotExist:
                    logger.error("\tUnable to find patient with mrn %s for file %s." % (mrn, filename))
                    continue
                
                details["patient_alias"] = patient.alias
            
            if not details.has_key("patient_name"):
                name = ds[0x10,0x10].value.strip()
                details["patient_name"] = name
            
            if not details.has_key("date"):
                rows = cursor.execute("select date from studyuid where cleaned=?",(study_uid,)).fetchall()
                study_date = None
                try:
                    study_date = rows[0][0]
                except IndexError, e:
                    logger.error("Unable to find study date for alias %s in identity database" % study_date)
                    conn.close()
                    sys.exit()
                details["date"] = datetime.date(int(study_date[0:4]),int(study_date[4:6]), int(study_date[6:8]))
            
            # This code will change the DICOM file.  It replaces the enumerated 
            # Patient ID (MRN) and Patient Name with Patient Alias
            if not options.dryrun:
                # Update the dicom file
                ds[0x10,0x10].value=details["patient_alias"]
                ds[0x10,0x20].value=details["patient_alias"]
                
                # Some files have overlays in them (data placed on top of the image),
                # it seems some of them have a VR written as "OB/OW" which
                # is not allowed. Pydicom refuses to write out the file if it 
                # encounters this. Changing it to OB in these cases
                if ds.has_key((0x6000,0x3000)) and len(ds[0x6000,0x3000].VR) > 2:
                    ds[0x6000,0x3000].VR = "OB"
                try:
                    ds.save_as(os.path.join(root,filename)) # Save over old DICOM file
                except Exception, e:
                    logger.error("For file %s, unable to change Patient ID to Patient alias: %s" % (os.path.join(root,filename),e))
    
    conn.close()
    print "Summary:"            
    for key in cache:
        del cache[key]["series"]
        print "%s : %s" % (key,cache[key])
    return cache

# This function modifies cache...
# returns a set of anonymized study_ids that were successfully hooked up
# PLEASE TAKE NOTE: This function is very customized to our internal database, it will not work for your institution
# the function takes the cache data structure and hooks up the de-identified studies
# with an existing de-identified database. 
# It is also responsible for setting the image as "published" to production and can set other attributes 
# like number of image in study
# This code will be refactored to be more flexible in the future, but for now the function will need to 
# modified in place
@transaction.commit_on_success
def add_studies(options, cache):
    connected_studies = set()
    logger = logging.getLogger("loadstudies")
    now = datetime.datetime.now()
    cursor = connections['staging'].cursor()
                          
    for study in cache:
        #study_date = cache[study]['date']
        order_ids = None

        # I am not sure that study -> accession is a one to one mapping, but I just need to find one 
        # accession number in the study that is associated to an Encounter and that is good enough.

        for accession in cache[study]['accession']:
            accession = str(accession)
            cursor.execute("select P.pat_enc_csn_id from clarity_imaging_accessions A inner join clarity_imaging_procedures P on (P.order_proc_id=A.order_proc_id) where A.acc_num = %s",[accession])
            rows = cursor.fetchall();
            if rows != None:
                order_ids =  [str(x[0]) for x in rows]
                break
        else:
            logger.error("Unable to find a valid accession number from %s in clarity_imaging_accessions for study %s" % (cache[study]['accession'], study))
            continue
        # from what I can tell some orders (of which there can be many to 1
        # accession, as well as more than one accession on one order) that pair
        # up to more than one encounter
        placeholder = "%s"
        placeholders = ", ".join(placeholder for unused in order_ids)
        q =  "select target_id from core_datasource where id in (select max(id) from core_datasource where (field_1 ='mriencounter.pat_enc_csn_id' or field_1 = 'ctencounter.pat_enc_csn_id' or field_1 = 'encounter.pat_enc_csn_id') and target='staging_encounter' and id_1 in (%s) group by id_1)" % placeholders
        cursor.execute(q, order_ids)

        rows = cursor.fetchall()
        if rows:
            encounter_ids = [int(x[0]) for x in rows]
            encounter_ids.sort();
            encounter_id = encounter_ids[len(encounter_ids)-1]
        else:
            logging.error("Unable to find encounter based on order ids %s for study %s." % (order_ids, study))
            continue 
        
        encounter = Encounter.objects.get(id=encounter_id)
        try: 
            if (encounter.patient.alias != cache[study]["patient_alias"]):
                logger.error("%s does not match patient alias %s for study %s." % (encounter, cache[study]["patient_alias"], study))
                continue
        except KeyError:
            logger.error("Patient alias not found for study %s" % study)
            continue

        cache[study]['encounter_id'] = encounter.pk
        # We have the correct encounter. Check to see if this study is on the encounter already
        try:
            rs = encounter.radiologystudy_set.get(original_study_uid = cache[study]["orig_study_uid"])
        except ObjectDoesNotExist:
            try:
                # study was not on encounter, just find the study and hook it up,
                # this is the most likely scenario
                rs = RadiologyStudy.objects.get(original_study_uid = cache[study]["orig_study_uid"])
                rs.encounter = encounter;
            except ObjectDoesNotExist:
                logging.error("Unable to find radiology study. It must exist prior to running this script.")
                continue
        # set attributes on rs
        rs.patient = encounter.patient
        rs.created = now
        rs.modified = now
        rs.study_uid = study
        rs.number_of_series=cache[study]['num_series']
        rs.total_images=cache[study]['num_images']
        rs.modality=cache[study]['modality']
        rs.image_published = True
        rs.pub_date = rs.pub_date or now
        rs.sop_class=cache[study]["sop_class_uid"]
        
        connected_studies.add(study.strip())
        
        logger.info("Processing study %s, %s" % (study,rs))
        if not options.dryrun:
            rs.save()
    return connected_studies
    


    def move_failed_studies(valid, directory, faildir):
        for root, dirs, files in os.walk(directory):  
           for filename in files:
               try:
                    ds = dicom.read_file(os.path.join(root, filename))
                    study_uid = ds[0x20,0xD].value.strip() 
               except IOError, e0:
                    study_uid = "<unable to read>"

               if study_uid == "<unable to read>" or not study_uid in valid:
                   try:
                      shutil.move(os.path.join(root,filename), faildir)
                   except IOError, e1:
                      print "Unable to move file %s with study_uid %s. Trying to move because it failed to be reconciled with a patient or an error occurred while reading the file." % (filename, study_uid)


def main():
    parser = OptionParser()
    parser.add_option("-d", "--directory", default=None, dest="directory", action="store", type="string", help="Directory containing dicom files")
    parser.add_option("-i", "--identity", default=None, dest="db", action="store", type="string", help="sqlite3 identity database")
    parser.add_option("-p", "--practice", default=False, dest="dryrun", action="store_true", help="Practice run without saving to AudGenDB database.")
    parser.add_option("-v", "--verbose",  default=False,dest="verbose", action="store_true", help="Print detailed info about encounters found.")
    parser.add_option("-w", "--window", default=3, dest="days", action="store", type="int", help="Window in days used to determine if a study should be attached to an encounter. Default is 3.")
    parser.add_option("-s", "--scanonly", default=False, dest="scanonly", action="store_true", help="Just scan dicom files and print summary.")
    parser.add_option("-f", "--faildir", default="no_encounter", dest="faildir", action="store", help="Directory to place studies that cannot be hooked to an encounter, defaults to no_encounter.")
    (options, args) = parser.parse_args()

    if options.db == None:
        print "Please specify an identity sqlite database using the -i flag."
        sys.exit()
    if options.directory == None:
        print "Please specify a directory containing the DICOM files using the -d flag."
        sys.exit()
        
    if options.dryrun:
        print "DRY RUN, will not make any permanent changes."
    
    if options.scanonly:
        options.dryrun = True

    if not os.path.exists(options.faildir):
        os.makedirs(options.faildir)
    
    logger = logging.getLogger("loadstudies")
    logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    if options.verbose:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.ERROR)
    logger.addHandler(ch)
    
    cache = scan_dicom_files(options)
    
    if options.scanonly:
        sys.exit()

    valid = add_studies(options, cache)
    if not options.dryrun:
        move_failed_studies(valid, options.directory, options.faildir)
    
    logger.info("Completed.")
    

if __name__ == "__main__":
    main()

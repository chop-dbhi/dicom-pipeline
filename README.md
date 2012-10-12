# DICOM Anonymization Pipeline


## What is the DICOM Anonymization pipeline

This is a software pipeline meant to perfom the following steps on on DICOM studies after they have beenreviewed with [django-dicom-review](https://github.com/cbmi/django-dicom-review)

1. Pull the studies from a staging (identified) PACS
1. Anonymize the studies
1. Integrate with existing research databases
1. Push the studies to a research PACS

The pipeline records information about each step using log files in a time stamped directory (more details to follow). It is capable of restarting a run from a failed step.


<center>
<img src="https://raw.github.com/cbmi/dicom-pipeline/master/pipeline-flowchart.png"/>
</center>


## Caveats
1. The integration step described above will be highly variable and depend on your task and environment. Currently this step is performed in the function add_studies with the loadstudies.py file. There are plans to make this portion easier to extend, but for now if you need to integrate with an existing database you will need look at the example provided (which is completely dependent on our applications and database schemas) and re-implement the function. 

## Architecture Assumptions

This pipeline assumes you have two image archives, one where identified images are stored (staging) and one where the de-identified images will be stored (production). It is assumed that you are running the [django-dicom-review](https://github.com/cbmi/django-dicom-review) application so that it serves up to reviewers images from the identified staging archive, and this pipeline will be pushing to the production staging archive.

## Pre-requisites not automatically installed

1. rvm must be installed and activated. The following versions of ruby must be installed within rvm (using ```rvm install <version #>```)
    * 1.8.7
        * install json and sqlite3 gems
    * 1.9.2

1. A recent version of Java. 

1. The [dcm4che2 toolkit](http://sourceforge.net/projects/dcm4che/files/dcm4che2/) must be downloaded and the bin directory from the toolkit must be on the system path.

1. Python version 2.7.1 (2.6 may work, but has not been tested). Pip must also be installed. It is highly recommended that the pipeline be installed in a clean virtualenv.
1. git
1. **VERY IMPORTANT** The value you are using for "LOCAL_AE", which by default is "DCMQR" (but can be changed in your local_settings.py file, see below) must be setup on your staging PACS to point to the IP address of the machine the pipeline is running on. If you are using DCM4CHEE this can be done via the AE Management tool on the web console. If this is not set properly you could **send identified DICOM data to the wrong machine**.

## Installation
Run the following commands to install the pipeline. If you are using a virtualenv, you may want to clone it into that directory.
```
git clone https://github.com/cbmi/dicom-pipeline.git dicom_pipeline
cd dicom_pipeline
git submodule update --init
pip install -U -r requirements.txt
```
Once this is done, you will need to place a valid local_settings.py in your root directory. 


## Setup your local_settings.py file
This settings file is used by both the Django ORM to read and write to the models that represent your studies and the DICOM utilities that receive and push the actual files to the PACS.

In the root directory of the pipeline repository you will find a local_settings.sample.py. Rename this file local_settings.py and fill out as appropriate. The comments within the file should explain what each value represents. Again, the "LOCAL_AE" value in this file must be setup properly on your staging PACS as described in the pre-requisites section.

## Running the pipeline
If you have an existing identity.db (which is used by the anonymizer), it must be in the pipeline root directory. Otherwise it will create a new one, and it will not be able to take advantage of any previous mappings it made. For example, if you use the same identity.db file, and the anonymizer previously mapped identified Study UID 1 to anonymized Study UID 0, it will continue to use that same mapping in the current round of anonymizations. If you do not have the identity.db file, STUDY UID 1 will be re-assigned a new anonymized Study UID if encountered. 

The pipeline.py file has a few options, including the ability to limit the number of studies processed (-m), restarting the last pipeline attempt instead of starting a new one (-r), and running a practice run that makes no permanent changes (-p). Use the --help option to see details on all options.

From the root directory of the pipeline git repository, run the following command

```python pipeline.py```

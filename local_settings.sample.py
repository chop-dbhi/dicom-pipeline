# This will be the AE (DICOM Application Entity) of the DICOM server started on
# this computer to receive the identified DICOM files from the staging PACS
LOCAL_AE = "DCMQR"
# The AE of your staging PACS
STAGE_AE = "DCM4CHEE"
# The AE of your production PACS
PROD_AE = "DCM4CHEE"
# IP address of this machine. Must be reachable from your staging PACS
LOCAL_HOST = ""
# IP address or hostname of your staging PACS
STAGE_HOST = ""
# IP address or hostname of your production PACS
PROD_HOST =  ""
# DICOM ports for your local receiving server, staging PACS, and production
# PACS. Should not have to change unless you use non-standard PACS setup
DEFAULT_PORT = 11112
STAGE_PORT = DEFAULT_PORT
PROD_PORT = DEFAULT_PORT
LOCAL_PORT = DEFAULT_PORT
# DICOM root to be used when anonymizing DICOM files.
DICOM_ROOT = ""

######### Django settings
INSTALLED_APPS = (os.path.split(os.path.split(__file__)[0])[1],)

# Define your staging database parameters here
staging_database = {
    'ENGINE': '',
    'NAME': '',
    'USER': '',
    'PASSWORD': '',
    'HOST': '',
    'PORT': '',
}

DATABASES = {
    'default': staging_database,
     # define your production database parameters here.
	 # this will only be used if you manually execute the copytoprod.py script
    'production': {
        'ENGINE': '',
        'NAME': '',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
    'staging': staging_database
}

DATABASE_ROUTERS = (
    'routers.ProductionDataRouter',
    'routers.StagingDataRouter',
)

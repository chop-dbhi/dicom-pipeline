from django.db.models import Count
from django.conf import settings
import loader

def associate_to_existing_studies(candidate_studies, user, annotation_class = None):
    return studies

def another_hook(overview):
    pass

registry = loader.Registry(default=one_per_year, default_name = "one per year")
#registry.register(lists, name = "lists")

loader.autodiscover('extra_hooks')

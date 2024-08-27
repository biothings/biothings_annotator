"""
Applicaton metadata manipulation and configuration methods
"""

import sanic
from sanic_ext.extensions.openapi.definitions import Contact, Info, Tag
from sanic_ext.extensions.openapi.types import Definition
from sanic_ext.utils.route import remove_nulls


def apply_openapi_metadata(application: sanic.Sanic):
    """
    Method for applying our metadata from the application.
    We're wishing to avoid a static metadata file so we'll
    have to do some overriding of the specification builder
    with the parameters we wish in python rather than statically
    via a JSON or YAML file. If that changes in the future,
    please replace this code with a hard-coded file.
    """

    # Description
    specification_builder = application.ext.openapi

    # Info override
    specification_builder._build_info = _build_info

    # Tags
    annotation_tags = {
        "gene_tag": "gene",
        "chemical_tag": "chemical",
        "drug_tag": "drug",
        "disease_tag": "disease",
        "phenotype_tag": "phenotype",
        "annotation_tag": "annotation",
        "translator_tag": "translator",
    }
    for tag_key, tag_name in annotation_tags.items():
        specification_builder.tags[tag_key] = Tag(name=tag_name)

    # Servers
    production_server = {
        "url": "https://biothings.ncats.io/annotator",
        "description": "Production Server",
        "x-maturity": "production",
    }
    staging_server = {
        "url": "https://biothings.test.transltr.io/annotator",
        "description": "Staging Server",
    }
    integration_server = {
        "url": "http://biothings.ci.transltr.io/annotator",
        "description": "CI Server",
    }
    server_instances = [
        AnnotationServer(**production_server),
        AnnotationServer(**staging_server),
        AnnotationServer(**integration_server),
    ]
    application.ext.openapi._servers = server_instances


class AnnotationServer(Definition):
    url: str
    description: str


def _build_info() -> Info:
    """
    Overridden method for info building.

    At the moment it forces the `Info` object
    that's created to not support specification
    extension fields so we have to supplant the current
    method with this one at runtime before building

    This method is called by the `SpecificationBuilder`
    instance in the `build` method
    """
    # Contact
    contact_mapping = {
        "email": "help@biothings.io",
        "name": "BioThings Team",
        "x-id": "https://github.com/biothings",
        "x-role": "responsible developers",
    }
    openapi_contact = Contact(**contact_mapping)

    x_translator = {"component": "Utility", "team": ["Service Provider"]}
    info_mapping = {
        "contact": openapi_contact,
        "description": "Translator Annotation Service",
        "termsOfService": "https://biothings.io/about",
        "title": "Translator Annotation Service",
        "version": "1.0",
        "x-translator": x_translator,
    }
    info_mapping = remove_nulls(info_mapping, deep=False)
    openapi_info = Info(**info_mapping)
    return openapi_info

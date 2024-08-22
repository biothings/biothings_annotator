"""
Applicaton metadata manipulation and configuration methods
"""

from textwrap import dedent

import sanic
from sanic_ext.extensions.openapi.definitions import Server, Tag


def apply_openapi_metadata(application: sanic.Sanic):
    apply_openapi_description(application)
    apply_openapi_tags(application)
    apply_openapi_server(application)


def apply_openapi_description(application: sanic.Sanic):
    application.ext.openapi.describe(
        "Biothings Annotator Service",
        version="0.0.1",
        description=dedent(
            """
            # Info
            contact:
                email: help@biothings.io
                name: BioThings Team
                x-id: https://github.com/biothings
                x-role: responsible developers
            description: Translator Annotation Service.
            termsOfService: https://biothings.io/about
            title: Translator Annotation Service
            version: '1.0'
            x-translator:
                component: Utility
                team:
                    Service Provider
            """
        ),
    )


def apply_openapi_tags(application: sanic.Sanic) -> None:
    """
    Updates the openAPI tags for the biothings annotator application
    instance
    """
    application.ext.openapi.tags["gene_tag"] = Tag("gene")
    application.ext.openapi.tags["chemical_tag"] = Tag("chemical")
    application.ext.openapi.tags["drug_tag"] = Tag("drug")
    application.ext.openapi.tags["disease_tag"] = Tag("disease")
    application.ext.openapi.tags["phenotype_tag"] = Tag("phenotype")
    application.ext.openapi.tags["annotation_tag"] = Tag("annotation")
    application.ext.openapi.tags["translator_tag"] = Tag("translator")


def apply_openapi_server(application: sanic.Sanic) -> None:
    """
    Updates the openAPI servers for the biothings annotator application
    instance
    """
    server_instances = [
        Server(
            url="https://biothings.ncats.io/annotator",
            description="Production Server",
            variables={"x-maturity": "production"},
        ),
        Server(
            url="http://biothings.test.transltr.io/annotator",
            description="Staging Server",
        ),
        Server(
            url="http://biothings.ci.transltr.io/annotator",
            description="CI Server",
        ),
    ]
    application.ext.openapi._servers = server_instances

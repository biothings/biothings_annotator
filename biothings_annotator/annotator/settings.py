"""
Defines the mapping from the biolink model to the Biothings data model
"""

SERVICE_PROVIDER_API_HOST = "https://biothings.ci.transltr.io"

QUERY_BACKEND = "biothings"
QUERY_BACKEND_ENV = "ANNOTATOR_QUERY_BACKEND"
SUPPORTED_QUERY_BACKENDS = ("biothings", "elasticsearch")
QUERY_BACKEND_ALIASES = {"es": "elasticsearch"}

BIOTHINGS_SOURCE_LIST_PATH = "api/list"
BIOTHINGS_SOURCE_DISCOVERY_TIMEOUT = 5
BIOTHINGS_SOURCE_DISCOVERY_TTL = 60
BIOTHINGS_SOURCE_DISCOVERY_ERROR_TTL = 5

ELASTICSEARCH_CONNECTION = "ci"
CI_LOCAL_FORWARD_ELASTICSEARCH_CONNECTION = {
    "host": "http://localhost:9200",
    "headers": {"Host": "core-components-es.ci.transltr.io"},
}
ELASTICSEARCH_CONNECTIONS = {
    "local": {
        "host": "http://localhost:9200",
        "headers": {},
    },
    "ci": {
        "host": "http://elasticsearch.es-core-components.svc.cluster.local:9200",
        "headers": {},
    },
    "ci_local_forward": CI_LOCAL_FORWARD_ELASTICSEARCH_CONNECTION,
    # Deprecated alias for compatibility with existing local-forward overrides.
    "ci_forward": CI_LOCAL_FORWARD_ELASTICSEARCH_CONNECTION,
}
ELASTICSEARCH_REQUEST_TIMEOUT = 30
ELASTICSEARCH_QUERY_SIZE = 10
ELASTICSEARCH_QUERY_BATCH_SIZE = 1000
DOCUMENT_METADATA_REQUEST_TIMEOUT = 2.0


BIOLINK_PREFIX_to_BioThings = {
    # "scopes" contains BioThings query scopes. "elasticsearch_scopes" overrides
    # those scopes with exact index field names when the two backends use different
    # vocabularies. Keeping the mappings separate prevents numeric fields such as
    # "retired" from being queried with non-numeric identifiers without losing hits
    # stored in nested Elasticsearch leaf fields.
    "NCBIGene": {"type": "gene", "scopes": ["entrezgene", "retired"]},
    # "HGNC": {"type": "gene", "field": "HGNC"},
    "ENSEMBL": {
        "type": "gene",
        "scopes": ["ensemblgene"],
        "elasticsearch_scopes": ["ensembl.gene"],
    },
    "UniProtKB": {
        "type": "gene",
        "scopes": ["uniprot", "accession"],
        "elasticsearch_scopes": ["uniprot.Swiss-Prot", "uniprot.TrEMBL"],
    },
    "INCHIKEY": {"type": "chem"},
    "CHEMBL.COMPOUND": {
        "type": "chem",
        "field": "chembl.molecule_chembl_id",
        # "converter": lambda x: x.replace("CHEMBL.COMPOUND:", "CHEMBL"),
    },
    "PUBCHEM.COMPOUND": {"type": "chem", "field": "pubchem.cid"},
    "CHEBI": {"type": "chem", "field": "chebi.id", "keep_prefix": True},
    "UNII": {"type": "chem", "field": "unii.unii"},
    "DRUGBANK": {"type": "chem", "field": "drugbank.id"},
    "MONDO": {"type": "disease", "field": "mondo.mondo", "keep_prefix": True},
    "DOID": {"type": "disease", "field": "disease_ontology.doid", "keep_prefix": True},
    "HP": {"type": "phenotype", "field": "hp", "keep_prefix": True},
    # PubMed is a standalone source whose documents use the full CURIE as _id.
    # BioThings availability is discovered dynamically from its API source list.
    "PMID": {
        "type": "pubmed",
        "scopes": ["_id"],
        "keep_prefix": True,
    },
    # DOI and PMCID are carried in the pubmed.identifiers array rather than the
    # document _id, so they need the identifiers scope instead of PMID's _id
    # scope. Babel's canonical prefix casing is lowercase "doi" and uppercase
    # "PMC"; the alternate casings are registered because _scopes_for_prefix
    # looks the prefix up exactly and an unregistered prefix is silently skipped
    # on the bulk and TRAPI paths. The index normalizes identifiers
    # case-insensitively, so the value itself needs no casing variants.
    "doi": {"type": "pubmed", "scopes": ["pubmed.identifiers"], "keep_prefix": True},
    "DOI": {"type": "pubmed", "scopes": ["pubmed.identifiers"], "keep_prefix": True},
    "PMC": {"type": "pubmed", "scopes": ["pubmed.identifiers"], "keep_prefix": True},
    "pmc": {"type": "pubmed", "scopes": ["pubmed.identifiers"], "keep_prefix": True},
}


ANNOTATOR_CLIENTS = {
    #todo  snapshots restorable to CoCo ES - ask Everaldo
    #todo  expose options to frontend usage to switch backend
    "gene": {
        "client": {
            "configuration": {"biothing_type": "gene"},  # the kwargs passed to biothings_client.get_client
            "endpoint": None,
            "instance": None,
        },
        "elasticsearch": {"index": "gene", "instance": None},
        "fields": [
            "name",
            "symbol",
            "summary",
            "type_of_gene",
            "MIM",
            "HGNC",
            "MGI",
            "RGD",
            "alias",
            "go.BP",
            "go.MF",
            "interpro",
            "pharos",
            "taxid",
        ],
        "scopes": ["entrezgene", "ensemblgene", "uniprot", "accession", "retired"],
        "elasticsearch_scopes": [
            "entrezgene",
            "ensembl.gene",
            "uniprot.Swiss-Prot",
            "uniprot.TrEMBL",
            "retired",
        ],
    },
    "chem": {
        "client": {
            "configuration": {"biothing_type": "chem"},  # the kwargs passed to biothings_client.get_client
            "endpoint": None,
            "instance": None,
        },
        "elasticsearch": {"index": "chem", "instance": None},
        "fields": [
            # IDs
            "pubchem.cid",
            "pubchem.inchikey",
            "chembl.molecule_chembl_id",
            "drugbank.id",
            "chebi.id",
            "unii.unii",
            # "chembl.unii",
            # Names
            "chebi.name",
            "chembl.pref_name",
            # Descriptions
            "chebi.definition",
            "unii.ncit",
            "unii.ncit_description",
            # Structure
            "chebi.iupac",
            "chembl.smiles",
            "pubchem.inchi",
            "pubchem.molecular_formula",
            "pubchem.molecular_weight",
            # chemical types
            "chembl.molecule_type",
            "chembl.structure_type",
            # chebi roles etc
            "chebi.relationship",
            # drug info
            "unichem.rxnorm",  # drug name
            "pharmgkb.trade_names",  # drug name
            "chembl.drug_indications",
            "aeolus.indications",
            "chembl.drug_mechanisms",
            "chembl.atc_classifications",
            "chembl.max_phase",
            "chembl.first_approval",
            "drugcentral.approval",
            "chembl.first_in_class",
            "chembl.inorganic_flag",
            "chembl.prodrug",
            "chembl.therapeutic_flag",
            "chembl.withdrawn_flag",
            "chembl.availability_type",
            "drugcentral.drug_dosage",
            "ndc.routename",
            "ndc.producttypename",
            "ndc.pharm_classes",
            "ndc.proprietaryname",
            "ndc.nonproprietaryname",
        ],
        "scopes": ["_id", "chebi.id", "chembl.molecule_chembl_id", "pubchem.cid", "drugbank.id", "unii.unii"],
    },
    "disease": {
        "client": {
            "configuration": {"biothing_type": "disease"},  # the kwargs passed to biothings_client.get_client
            "endpoint": None,
            "instance": None,
        },
        "elasticsearch": {"index": "disease", "instance": None},
        "fields": [
            # IDs
            "disease_ontology.doid",
            "mondo.mondo",
            "umls.umls",
            # Names
            "disease_ontology.name",
            "mondo.label",
            # Description
            "mondo.definition",
            "disease_ontology.def",
            # Xrefs
            "mondo.xrefs",
            "disease_ontology.xrefs",
            # Synonyms
            "mondo.synonym",
            "disease_ontology.synonyms",
        ],
        "scopes": ["mondo.mondo", "disease_ontology.doid", "umls.umls"],
    },
    "phenotype": {
        "client": {"configuration": None, "endpoint": "hpo", "instance": None},
        "elasticsearch": {"index": "hpo", "instance": None},
        "fields": ["hp", "name", "annotations", "comment", "def", "subset", "synonym", "xrefs"],
        "scopes": ["hp"],
    },
    "pubmed": {
        # The endpoint is declared before deployment so API source discovery can
        # activate it without another annotator release.
        "client": {
            "configuration": None,
            "endpoint": "pubmed",
            "source": "pubmed",
            "instance": None,
        },
        "elasticsearch": {"index": "annotator-pubmed", "instance": None},
        "fields": [
            "pubmed.identifiers",
            "pubmed.journal.name",
            "pubmed.journal.abbr",
            "pubmed.title",
            "pubmed.vol",
            "pubmed.iss",
            "pubmed.pub_date",
            "pubmed.pubdate_raw",
            "pubmed.abstract",
        ],
        "scopes": ["_id"],
    },
    # This API append NCIT description to the existing data
    "ncit": {
        "client": {"configuration": None, "endpoint": "ncit", "instance": None},
        "elasticsearch": {"index": "ncit", "instance": None},
        "fields": ["def"],
        "scopes": ["_id"],
    },
    # This API captures the extra information that is not available in the main biothings API
    "extra": {
        "client": {"configuration": None, "endpoint": "annotator_extra", "instance": None},
        "elasticsearch": {"index": "annotator_extra", "instance": None},
        "scopes": ["_id"],
    },
}

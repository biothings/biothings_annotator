"""
Defines the mapping from the biolink model to the Biothings data model
"""

SERVICE_PROVIDER_API_HOST = "https://biothings.ci.transltr.io"


BIOLINK_PREFIX_to_BioThings = {
    "NCBIGene": {"type": "gene", "field": "entrezgene"},
    # "HGNC": {"type": "gene", "field": "HGNC"},
    "ENSEMBL": {"type": "gene", "field": "ensembl.gene"},
    "UniProtKB": {"type": "gene", "field": "uniprot.Swiss-Prot"},
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
}


ANNOTATOR_CLIENTS = {
    "gene": {
        "client": {"biothing_type": "gene"},  # the kwargs passed to biothings_client.get_client
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
            "interpro",
            "pharos",
            "taxid",
        ],
        "scopes": ["entrezgene", "ensemblgene", "uniprot", "accession", "retired"],
    },
    "chem": {
        "client": {"biothing_type": "chem"},
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
            "cheml.withdrawn_flag",
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
        "client": {"biothing_type": "disease"},
        "fields": [
            # IDs
            "disease_ontology.doid",
            "mondo.mondo",
            "umls.umls",
            # Names
            "disease_ontology.name",
            "mondo.label"
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
        "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/hpo"},
        "fields": ["hp", "name", "annotations", "comment", "def", "subset", "synonym", "xrefs"],
        "scopes": ["hp"],
    },
    # This API append NCIT description to the existing data
    "ncit": {
        "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/ncit"},
        "fields": ["def"],
        "scopes": ["_id"],
    },
    # This API captures the extra information that is not available in the main biothings API
    "extra": {
        "client": {"url": f"{SERVICE_PROVIDER_API_HOST}/annotator_extra"},
        "scopes": ["_id"],
    },
}

"""
Defines the mapping from the biolink model to the Biothings data model
"""

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

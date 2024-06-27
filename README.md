# biothings annotator

Annotation service for the Translator Project. Originally apart of the 
[pending.api](https://github.com/biothings/pending.api/blob/b7a5a5cb2a890da8563a105e1da1215d7eb09e55/web/handlers/annotator.py),
we've broken it out into it's own service


### Installation

```shell
git clone https://github.com/biothings/biothings_annotator
python3 -m venv biothings_annotator
cd biothings_annotator
pip install .
```

### Structure
```shell 
├── biothings_annotator
│   ├── annotator.py
│   ├── application
│   │   ├── configuration
│   │   ├── handlers
│   │   ├── __init__.py
│   │   └── sanic.py
│   ├── biolink.py
│   ├── exceptions.py
│   ├── __init__.py
│   ├── __main__.py
│   └── transformer.py
└── tests
    ├── conftest.py
    ├── data
    ├── test_curie.py
    ├── test_query.py
    ├── test_transformer.py
    └── test_trapi.py
```
`biothings_annotator` is the main module for the python package. Separated between the annotator logic and web handler logic. The annotator logic primarily exists within `annotator.py` and `transformer.py`. Whereas the web server application is defined entirely within `application` directory. 


### Invocation
The `__main__.py` defines the entrypoint to the module for running the `sanic` web server. Run
`python3 biothings_annotator` to run the annotator service


### Tests
The tests are implemented with `pytest` in mind. To install the test dependencies `pip install
.[tests]`. 

- Test Overview `pytest --setup-plan`

```
(biothings_annotator) ~/biothings_annotator$ python3 -m pytest tests/ --setup-plan
==================================================================================== test session starts ====================================================================================
platform linux -- Python 3.10.12, pytest-8.2.2, pluggy-1.5.0 -- ~/biothings_annotator/bin/python3
cachedir: .pytest_cache
rootdir: ~/biothings_annotator
configfile: pyproject.toml
collected 51 items

tests/test_curie.py::test_curie_parsing[NCBIGene]
        SETUP    F curie_prefix['NCBIGene']
        tests/test_curie.py::test_curie_parsing[NCBIGene] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['NCBIGene']
tests/test_curie.py::test_curie_parsing[ENSEMBL]
        SETUP    F curie_prefix['ENSEMBL']
        tests/test_curie.py::test_curie_parsing[ENSEMBL] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['ENSEMBL']
tests/test_curie.py::test_curie_parsing[UniProtKB]
        SETUP    F curie_prefix['UniProtKB']
        tests/test_curie.py::test_curie_parsing[UniProtKB] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UniProtKB']
tests/test_curie.py::test_curie_parsing[INCHIKEY]
        SETUP    F curie_prefix['INCHIKEY']
        tests/test_curie.py::test_curie_parsing[INCHIKEY] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['INCHIKEY']
tests/test_curie.py::test_curie_parsing[CHEMBL.COMPOUND]
        SETUP    F curie_prefix['CHEMBL.COMPOUND']
        tests/test_curie.py::test_curie_parsing[CHEMBL.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEMBL.COMPOUND']
tests/test_curie.py::test_curie_parsing[PUBCHEM.COMPOUND]
        SETUP    F curie_prefix['PUBCHEM.COMPOUND']
        tests/test_curie.py::test_curie_parsing[PUBCHEM.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['PUBCHEM.COMPOUND']
tests/test_curie.py::test_curie_parsing[CHEBI]
        SETUP    F curie_prefix['CHEBI']
        tests/test_curie.py::test_curie_parsing[CHEBI] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEBI']
tests/test_curie.py::test_curie_parsing[UNII]
        SETUP    F curie_prefix['UNII']
        tests/test_curie.py::test_curie_parsing[UNII] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UNII']
tests/test_curie.py::test_curie_parsing[DRUGBANK]
        SETUP    F curie_prefix['DRUGBANK']
        tests/test_curie.py::test_curie_parsing[DRUGBANK] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DRUGBANK']
tests/test_curie.py::test_curie_parsing[MONDO]
        SETUP    F curie_prefix['MONDO']
        tests/test_curie.py::test_curie_parsing[MONDO] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['MONDO']
tests/test_curie.py::test_curie_parsing[DOID]
        SETUP    F curie_prefix['DOID']
        tests/test_curie.py::test_curie_parsing[DOID] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DOID']
tests/test_curie.py::test_curie_parsing[HP]
        SETUP    F curie_prefix['HP']
        tests/test_curie.py::test_curie_parsing[HP] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['HP']
tests/test_query.py::test_annotation_client[gene]
        SETUP    F node_type['gene']
        tests/test_query.py::test_annotation_client[gene] (fixtures used: node_type)
        TEARDOWN F node_type['gene']
tests/test_query.py::test_annotation_client[chem]
        SETUP    F node_type['chem']
        tests/test_query.py::test_annotation_client[chem] (fixtures used: node_type)
        TEARDOWN F node_type['chem']
tests/test_query.py::test_annotation_client[disease]
        SETUP    F node_type['disease']
        tests/test_query.py::test_annotation_client[disease] (fixtures used: node_type)
        TEARDOWN F node_type['disease']
tests/test_query.py::test_annotation_client[phenotype]
        SETUP    F node_type['phenotype']
        tests/test_query.py::test_annotation_client[phenotype] (fixtures used: node_type)
        TEARDOWN F node_type['phenotype']
tests/test_query.py::test_annotation_client[NULL]
        SETUP    F node_type['NULL']
        tests/test_query.py::test_annotation_client[NULL] (fixtures used: node_type)
        TEARDOWN F node_type['NULL']
tests/test_query.py::test_biothings_query[NCBIGene]
        SETUP    F curie_prefix['NCBIGene']
        tests/test_query.py::test_biothings_query[NCBIGene] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['NCBIGene']
tests/test_query.py::test_biothings_query[ENSEMBL]
        SETUP    F curie_prefix['ENSEMBL']
        tests/test_query.py::test_biothings_query[ENSEMBL] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['ENSEMBL']
tests/test_query.py::test_biothings_query[UniProtKB]
        SETUP    F curie_prefix['UniProtKB']
        tests/test_query.py::test_biothings_query[UniProtKB] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UniProtKB']
tests/test_query.py::test_biothings_query[INCHIKEY]
        SETUP    F curie_prefix['INCHIKEY']
        tests/test_query.py::test_biothings_query[INCHIKEY] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['INCHIKEY']
tests/test_query.py::test_biothings_query[CHEMBL.COMPOUND]
        SETUP    F curie_prefix['CHEMBL.COMPOUND']
        tests/test_query.py::test_biothings_query[CHEMBL.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEMBL.COMPOUND']
tests/test_query.py::test_biothings_query[PUBCHEM.COMPOUND]
        SETUP    F curie_prefix['PUBCHEM.COMPOUND']
        tests/test_query.py::test_biothings_query[PUBCHEM.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['PUBCHEM.COMPOUND']
tests/test_query.py::test_biothings_query[CHEBI]
        SETUP    F curie_prefix['CHEBI']
        tests/test_query.py::test_biothings_query[CHEBI] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEBI']
tests/test_query.py::test_biothings_query[UNII]
        SETUP    F curie_prefix['UNII']
        tests/test_query.py::test_biothings_query[UNII] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UNII']
tests/test_query.py::test_biothings_query[DRUGBANK]
        SETUP    F curie_prefix['DRUGBANK']
        tests/test_query.py::test_biothings_query[DRUGBANK] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DRUGBANK']
tests/test_query.py::test_biothings_query[MONDO]
        SETUP    F curie_prefix['MONDO']
        tests/test_query.py::test_biothings_query[MONDO] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['MONDO']
tests/test_query.py::test_biothings_query[DOID]
        SETUP    F curie_prefix['DOID']
        tests/test_query.py::test_biothings_query[DOID] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DOID']
tests/test_query.py::test_biothings_query[HP]
        SETUP    F curie_prefix['HP']
        tests/test_query.py::test_biothings_query[HP] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['HP']
tests/test_query.py::test_query_post_processing[entry-collection0-histogram0]
        SETUP    F search_keyword['entry']
        SETUP    F collection[[{'_id': 82, 'entry...'status': 'NORMAL'}]]
        SETUP    F histogram[{'compilation': [{'...status': 'NORMAL'}]}]
        tests/test_query.py::test_query_post_processing[entry-collection0-histogram0] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{'compilation': [{'...status': 'NORMAL'}]}]
        TEARDOWN F collection[[{'_id': 82, 'entry...'status': 'NORMAL'}]]
        TEARDOWN F search_keyword['entry']
tests/test_query.py::test_query_post_processing[entry-collection1-histogram1]
        SETUP    F search_keyword['entry']
        SETUP    F collection[[{'_id': 23, 'entry...us': 'NORMAL'}, ...]]
        SETUP    F histogram[{'builder': [{'_id'...s': 'NORMAL'}], ...}]
        tests/test_query.py::test_query_post_processing[entry-collection1-histogram1] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{'builder': [{'_id'...s': 'NORMAL'}], ...}]
        TEARDOWN F collection[[{'_id': 23, 'entry...us': 'NORMAL'}, ...]]
        TEARDOWN F search_keyword['entry']
tests/test_query.py::test_query_post_processing[NULL-collection2-histogram2]
        SETUP    F search_keyword['NULL']
        SETUP    F collection[[{'_id': 82, 'entry...'status': 'NORMAL'}]]
        SETUP    F histogram[{}]
        tests/test_query.py::test_query_post_processing[NULL-collection2-histogram2] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{}]
        TEARDOWN F collection[[{'_id': 82, 'entry...'status': 'NORMAL'}]]
        TEARDOWN F search_keyword['NULL']
tests/test_query.py::test_query_post_processing[NULL-collection3-histogram3]
        SETUP    F search_keyword['NULL']
        SETUP    F collection[[{}]]
        SETUP    F histogram[{}]
        tests/test_query.py::test_query_post_processing[NULL-collection3-histogram3] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{}]
        TEARDOWN F collection[[{}]]
        TEARDOWN F search_keyword['NULL']
tests/test_query.py::test_query_post_processing[NULL-collection4-histogram4]
        SETUP    F search_keyword['NULL']
        SETUP    F collection[[]]
        SETUP    F histogram[{}]
        tests/test_query.py::test_query_post_processing[NULL-collection4-histogram4] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{}]
        TEARDOWN F collection[[]]
        TEARDOWN F search_keyword['NULL']
tests/test_query.py::test_query_post_processing[-collection5-histogram5]
        SETUP    F search_keyword['']
        SETUP    F collection[[{}]]
        SETUP    F histogram[{}]
        tests/test_query.py::test_query_post_processing[-collection5-histogram5] (fixtures used: collection, histogram, search_keyword)
        TEARDOWN F histogram[{}]
        TEARDOWN F collection[[{}]]
        TEARDOWN F search_keyword['']
tests/test_transformer.py::test_annotation_transform[NCBIGene]
        SETUP    F curie_prefix['NCBIGene']
        tests/test_transformer.py::test_annotation_transform[NCBIGene] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['NCBIGene']
tests/test_transformer.py::test_annotation_transform[ENSEMBL]
        SETUP    F curie_prefix['ENSEMBL']
        tests/test_transformer.py::test_annotation_transform[ENSEMBL] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['ENSEMBL']
tests/test_transformer.py::test_annotation_transform[UniProtKB]
        SETUP    F curie_prefix['UniProtKB']
        tests/test_transformer.py::test_annotation_transform[UniProtKB] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UniProtKB']
tests/test_transformer.py::test_annotation_transform[INCHIKEY]
        SETUP    F curie_prefix['INCHIKEY']
        tests/test_transformer.py::test_annotation_transform[INCHIKEY] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['INCHIKEY']
tests/test_transformer.py::test_annotation_transform[CHEMBL.COMPOUND]
        SETUP    F curie_prefix['CHEMBL.COMPOUND']
        tests/test_transformer.py::test_annotation_transform[CHEMBL.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEMBL.COMPOUND']
tests/test_transformer.py::test_annotation_transform[PUBCHEM.COMPOUND]
        SETUP    F curie_prefix['PUBCHEM.COMPOUND']
        tests/test_transformer.py::test_annotation_transform[PUBCHEM.COMPOUND] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['PUBCHEM.COMPOUND']
tests/test_transformer.py::test_annotation_transform[CHEBI]
        SETUP    F curie_prefix['CHEBI']
        tests/test_transformer.py::test_annotation_transform[CHEBI] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['CHEBI']
tests/test_transformer.py::test_annotation_transform[UNII]
        SETUP    F curie_prefix['UNII']
        tests/test_transformer.py::test_annotation_transform[UNII] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['UNII']
tests/test_transformer.py::test_annotation_transform[DRUGBANK]
        SETUP    F curie_prefix['DRUGBANK']
        tests/test_transformer.py::test_annotation_transform[DRUGBANK] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DRUGBANK']
tests/test_transformer.py::test_annotation_transform[MONDO]
        SETUP    F curie_prefix['MONDO']
        tests/test_transformer.py::test_annotation_transform[MONDO] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['MONDO']
tests/test_transformer.py::test_annotation_transform[DOID]
        SETUP    F curie_prefix['DOID']
        tests/test_transformer.py::test_annotation_transform[DOID] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['DOID']
tests/test_transformer.py::test_annotation_transform[HP]
        SETUP    F curie_prefix['HP']
        tests/test_transformer.py::test_annotation_transform[HP] (fixtures used: curie_prefix)
        TEARDOWN F curie_prefix['HP']
tests/test_trapi.py::TestTrapiAnnotation::test_default
SETUP    S tmp_path_factory
SETUP    S temporary_data_storage (fixtures used: tmp_path_factory)
SETUP    S trapi_request (fixtures used: temporary_data_storage)
        tests/test_trapi.py::TestTrapiAnnotation::test_default (fixtures used: request, temporary_data_storage, tmp_path_factory, trapi_request)
tests/test_trapi.py::TestTrapiAnnotation::test_append
        tests/test_trapi.py::TestTrapiAnnotation::test_append (fixtures used: request, temporary_data_storage, tmp_path_factory, trapi_request)
tests/test_trapi.py::TestTrapiAnnotation::test_raw
        tests/test_trapi.py::TestTrapiAnnotation::test_raw (fixtures used: request, temporary_data_storage, tmp_path_factory, trapi_request)
tests/test_trapi.py::TestTrapiAnnotation::test_append_and_raw
        tests/test_trapi.py::TestTrapiAnnotation::test_append_and_raw (fixtures used: request, temporary_data_storage, tmp_path_factory, trapi_request)
TEARDOWN S trapi_request
TEARDOWN S temporary_data_storage
TEARDOWN S tmp_path_factory

===================================================================================== slowest durations =====================================================================================
0.00s setup    tests/test_query.py::test_query_post_processing[entry-collection1-histogram1]
0.00s setup    tests/test_curie.py::test_curie_parsing[NCBIGene]
0.00s teardown tests/test_trapi.py::TestTrapiAnnotation::test_append_and_raw
0.00s setup    tests/test_trapi.py::TestTrapiAnnotation::test_default
0.00s teardown tests/test_query.py::test_query_post_processing[entry-collection1-histogram1]
0.00s setup    tests/test_query.py::test_query_post_processing[entry-collection0-histogram0]
0.00s setup    tests/test_query.py::test_query_post_processing[NULL-collection2-histogram2]
0.00s setup    tests/test_query.py::test_query_post_processing[-collection5-histogram5]
0.00s setup    tests/test_query.py::test_query_post_processing[NULL-collection3-histogram3]
0.00s setup    tests/test_query.py::test_query_post_processing[NULL-collection4-histogram4]
0.00s teardown tests/test_query.py::test_query_post_processing[entry-collection0-histogram0]
0.00s teardown tests/test_query.py::test_query_post_processing[NULL-collection2-histogram2]
0.00s teardown tests/test_query.py::test_query_post_processing[-collection5-histogram5]
0.00s teardown tests/test_query.py::test_query_post_processing[NULL-collection3-histogram3]
0.00s teardown tests/test_query.py::test_query_post_processing[NULL-collection4-histogram4]
0.00s setup    tests/test_transformer.py::test_annotation_transform[NCBIGene]
0.00s teardown tests/test_curie.py::test_curie_parsing[NCBIGene]
0.00s setup    tests/test_curie.py::test_curie_parsing[ENSEMBL]
0.00s setup    tests/test_query.py::test_biothings_query[CHEBI]
0.00s setup    tests/test_query.py::test_biothings_query[ENSEMBL]
0.00s setup    tests/test_curie.py::test_curie_parsing[INCHIKEY]
0.00s setup    tests/test_query.py::test_biothings_query[CHEMBL.COMPOUND]
0.00s setup    tests/test_query.py::test_biothings_query[DRUGBANK]
0.00s setup    tests/test_query.py::test_biothings_query[UNII]
0.00s setup    tests/test_curie.py::test_curie_parsing[UniProtKB]
0.00s setup    tests/test_transformer.py::test_annotation_transform[MONDO]
0.00s setup    tests/test_query.py::test_annotation_client[gene]
0.00s setup    tests/test_trapi.py::TestTrapiAnnotation::test_raw
0.00s setup    tests/test_curie.py::test_curie_parsing[PUBCHEM.COMPOUND]
0.00s setup    tests/test_query.py::test_biothings_query[INCHIKEY]
0.00s setup    tests/test_curie.py::test_curie_parsing[HP]
0.00s setup    tests/test_curie.py::test_curie_parsing[CHEMBL.COMPOUND]
0.00s setup    tests/test_query.py::test_biothings_query[PUBCHEM.COMPOUND]
0.00s setup    tests/test_transformer.py::test_annotation_transform[UNII]
0.00s setup    tests/test_curie.py::test_curie_parsing[MONDO]
0.00s setup    tests/test_transformer.py::test_annotation_transform[PUBCHEM.COMPOUND]
0.00s setup    tests/test_query.py::test_annotation_client[chem]
0.00s setup    tests/test_curie.py::test_curie_parsing[CHEBI]
0.00s setup    tests/test_curie.py::test_curie_parsing[DRUGBANK]
0.00s setup    tests/test_query.py::test_biothings_query[MONDO]
0.00s setup    tests/test_transformer.py::test_annotation_transform[CHEBI]
0.00s setup    tests/test_query.py::test_biothings_query[NCBIGene]
0.00s setup    tests/test_query.py::test_biothings_query[HP]
0.00s setup    tests/test_curie.py::test_curie_parsing[DOID]
0.00s setup    tests/test_transformer.py::test_annotation_transform[UniProtKB]
0.00s setup    tests/test_transformer.py::test_annotation_transform[ENSEMBL]
0.00s setup    tests/test_query.py::test_annotation_client[NULL]
0.00s setup    tests/test_query.py::test_annotation_client[phenotype]
0.00s setup    tests/test_query.py::test_biothings_query[UniProtKB]
0.00s setup    tests/test_transformer.py::test_annotation_transform[CHEMBL.COMPOUND]
0.00s setup    tests/test_curie.py::test_curie_parsing[UNII]
0.00s setup    tests/test_transformer.py::test_annotation_transform[DRUGBANK]
0.00s setup    tests/test_transformer.py::test_annotation_transform[INCHIKEY]
0.00s setup    tests/test_query.py::test_biothings_query[DOID]
0.00s setup    tests/test_query.py::test_annotation_client[disease]
0.00s setup    tests/test_transformer.py::test_annotation_transform[DOID]
0.00s setup    tests/test_transformer.py::test_annotation_transform[HP]
0.00s teardown tests/test_query.py::test_biothings_query[INCHIKEY]
0.00s teardown tests/test_curie.py::test_curie_parsing[ENSEMBL]
0.00s teardown tests/test_curie.py::test_curie_parsing[INCHIKEY]
0.00s setup    tests/test_trapi.py::TestTrapiAnnotation::test_append
0.00s teardown tests/test_curie.py::test_curie_parsing[CHEBI]
0.00s teardown tests/test_query.py::test_annotation_client[gene]
0.00s teardown tests/test_curie.py::test_curie_parsing[UniProtKB]
0.00s teardown tests/test_query.py::test_biothings_query[HP]
0.00s teardown tests/test_query.py::test_annotation_client[chem]
0.00s teardown tests/test_transformer.py::test_annotation_transform[CHEBI]
0.00s teardown tests/test_curie.py::test_curie_parsing[DOID]
0.00s teardown tests/test_curie.py::test_curie_parsing[CHEMBL.COMPOUND]
0.00s teardown tests/test_query.py::test_biothings_query[CHEBI]
0.00s teardown tests/test_curie.py::test_curie_parsing[HP]
0.00s teardown tests/test_curie.py::test_curie_parsing[PUBCHEM.COMPOUND]
0.00s teardown tests/test_query.py::test_biothings_query[CHEMBL.COMPOUND]
0.00s teardown tests/test_transformer.py::test_annotation_transform[NCBIGene]
0.00s teardown tests/test_transformer.py::test_annotation_transform[CHEMBL.COMPOUND]
0.00s teardown tests/test_transformer.py::test_annotation_transform[INCHIKEY]
0.00s teardown tests/test_query.py::test_biothings_query[UniProtKB]
0.00s teardown tests/test_transformer.py::test_annotation_transform[HP]
0.00s teardown tests/test_query.py::test_biothings_query[PUBCHEM.COMPOUND]
0.00s teardown tests/test_curie.py::test_curie_parsing[DRUGBANK]
0.00s teardown tests/test_query.py::test_annotation_client[phenotype]
0.00s setup    tests/test_trapi.py::TestTrapiAnnotation::test_append_and_raw
0.00s teardown tests/test_query.py::test_biothings_query[UNII]
0.00s teardown tests/test_curie.py::test_curie_parsing[UNII]
0.00s teardown tests/test_transformer.py::test_annotation_transform[UNII]
0.00s teardown tests/test_query.py::test_annotation_client[disease]
0.00s teardown tests/test_transformer.py::test_annotation_transform[PUBCHEM.COMPOUND]
0.00s teardown tests/test_query.py::test_biothings_query[ENSEMBL]
0.00s teardown tests/test_query.py::test_biothings_query[DRUGBANK]
0.00s teardown tests/test_transformer.py::test_annotation_transform[ENSEMBL]
0.00s teardown tests/test_query.py::test_biothings_query[MONDO]
0.00s teardown tests/test_transformer.py::test_annotation_transform[UniProtKB]
0.00s teardown tests/test_transformer.py::test_annotation_transform[MONDO]
0.00s teardown tests/test_query.py::test_biothings_query[NCBIGene]
0.00s teardown tests/test_transformer.py::test_annotation_transform[DRUGBANK]
0.00s teardown tests/test_curie.py::test_curie_parsing[MONDO]
0.00s teardown tests/test_query.py::test_biothings_query[DOID]
0.00s teardown tests/test_query.py::test_annotation_client[NULL]
0.00s teardown tests/test_transformer.py::test_annotation_transform[DOID]
0.00s teardown tests/test_trapi.py::TestTrapiAnnotation::test_raw
0.00s teardown tests/test_trapi.py::TestTrapiAnnotation::test_default
0.00s teardown tests/test_trapi.py::TestTrapiAnnotation::test_append
```

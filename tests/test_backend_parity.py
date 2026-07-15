"""
Backend parity tests for BioThings and Elasticsearch query backends.

These tests use deterministic fake query clients so they validate the
annotator's backend-neutral behavior without depending on live services.
"""

from copy import deepcopy

import pytest

from biothings_annotator.annotator import transformer
from biothings_annotator.annotator.annotator import Annotator
from biothings_annotator.annotator.settings import ANNOTATOR_CLIENTS, BIOLINK_PREFIX_to_BioThings


ATC_ROWS = [
    {"atc": {"code": "A", "name": "Alimentary tract and metabolism"}},
    {"atc": {"code": "A01", "name": "Stomatological preparations"}},
    {"atc": {"code": "A01A", "name": "Stomatological preparations"}},
    {"atc": {"code": "A01AB", "name": "Antiinfectives and antiseptics for local oral treatment"}},
    {"atc": {"code": "A01AB02", "name": "Hydrogen peroxide"}},
    {"atc": {"code": "B", "name": "Blood and blood forming organs"}},
    {"atc": {"code": "B02", "name": "Antihemorrhagics"}},
    {"atc": {"code": "B02B", "name": "Vitamin K and other hemostatics"}},
    {"atc": {"code": "B02BC", "name": "Local hemostatics"}},
    {"atc": {"code": "B02BC01", "name": "Absorbable gelatin sponge"}},
]


class FakeQueryClient:
    def __init__(self, hits_by_query=None, atc_rows=None):
        self.hits_by_query = hits_by_query or {}
        self.atc_rows = atc_rows or []
        self.querymany_calls = []
        self.query_calls = []

    async def querymany(self, query_list, scopes, fields):
        query_list = list(query_list)
        self.querymany_calls.append(
            {
                "query_list": query_list,
                "scopes": deepcopy(scopes),
                "fields": deepcopy(fields),
            }
        )

        hits = []
        for query_id in query_list:
            query_hits = self.hits_by_query.get(query_id, [{"query": query_id, "notfound": True}])
            hits.extend(deepcopy(query_hits))
        return hits

    async def query(self, query, fields=None, fetch_all=False, size=None, skip=0):
        self.query_calls.append(
            {
                "query": query,
                "fields": fields,
                "fetch_all": fetch_all,
                "size": size,
                "skip": skip,
            }
        )

        async def _atc_iterator():
            for row in self.atc_rows:
                yield deepcopy(row)

        if fetch_all:
            return _atc_iterator()
        return {"took": 0, "total": 0, "max_score": None, "hits": []}


def make_client_registry():
    gene_hits = {
        "1017": [
            {
                "query": "1017",
                "_id": "1017",
                "_score": 99.0,
                "symbol": "CDK2",
                "name": "cyclin dependent kinase 2",
            },
            {
                "query": "1017",
                "_id": "12566",
                "_score": 8.0,
                "symbol": "Cdk2",
                "name": "cyclin-dependent kinase 2",
            },
        ],
        "9999": [{"query": "9999", "notfound": True}],
    }
    chem_hits = {
        "CHEMBL123": [
            {
                "query": "CHEMBL123",
                "_id": "CHEMBL123",
                "_score": 42.0,
                "chembl": {
                    "molecule_chembl_id": "CHEMBL123",
                    "drug_indications": [{"mesh_id": "D012345"}],
                    "atc_classifications": ["A01AB02"],
                },
                "pharmgkb": {"xrefs": {"atc": "A01AB02"}},
            }
        ],
        "2244": [
            {
                "query": "2244",
                "_id": "PUBCHEM2244",
                "_score": 34.0,
                "chembl": {
                    "drug_indications": [{"mesh_id": "MESH:D000001"}],
                    "atc_classifications": "B02BC01",
                },
            }
        ],
    }
    disease_hits = {
        "MONDO:0005148": [
            {
                "query": "MONDO:0005148",
                "_id": "MONDO:0005148",
                "_score": 12.0,
                "mondo": {"label": "type 2 diabetes mellitus"},
            }
        ],
    }
    extra_hits = {
        "CHEMBL123": [
            {
                "query": "CHEMBL123",
                "_id": "CHEMBL123",
                "extra_label": "single CHEMBL extra annotation",
            }
        ],
        "CHEMBL.COMPOUND:CHEMBL123": [
            {
                "query": "CHEMBL.COMPOUND:CHEMBL123",
                "_id": "CHEMBL.COMPOUND:CHEMBL123",
                "extra_label": "canonical CHEMBL extra annotation",
            }
        ],
        "PUBCHEM.COMPOUND:2244": [
            {
                "query": "PUBCHEM.COMPOUND:2244",
                "_id": "PUBCHEM.COMPOUND:2244",
                "extra_label": "canonical PubChem extra annotation",
            }
        ],
    }

    return {
        "biothings": {
            "gene": FakeQueryClient(gene_hits),
            "chem": FakeQueryClient(chem_hits),
            "disease": FakeQueryClient(disease_hits),
            "extra": FakeQueryClient(extra_hits, atc_rows=ATC_ROWS),
        },
        "elasticsearch": {
            "gene": FakeQueryClient(gene_hits),
            "chem": FakeQueryClient(chem_hits),
            "disease": FakeQueryClient(disease_hits),
            "extra": FakeQueryClient(extra_hits, atc_rows=ATC_ROWS),
        },
    }


def install_fake_query_clients(monkeypatch, registry):
    def _get_query_client(node_type, query_backend, api_host, elasticsearch_connection):
        del api_host, elasticsearch_connection
        return registry[query_backend][node_type]

    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", _get_query_client)


async def run_with_backend(backend, method_name, *args, **kwargs):
    annotator = Annotator()
    annotator.query_backend = backend
    annotator.elasticsearch_connection = "ci"
    method = getattr(annotator, method_name)
    return await method(*args, **kwargs)


@pytest.mark.asyncio
async def test_query_annotations_backend_parity_for_raw_grouped_hits(monkeypatch):
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    fields = ["symbol", "name"]
    biothings_result = await run_with_backend("biothings", "query_annotations", "gene", ["1017", "9999"], fields)
    elasticsearch_result = await run_with_backend(
        "elasticsearch", "query_annotations", "gene", ["1017", "9999"], fields
    )

    assert elasticsearch_result == biothings_result == {
        "1017": [
            {
                "query": "1017",
                "_id": "1017",
                "_score": 99.0,
                "symbol": "CDK2",
                "name": "cyclin dependent kinase 2",
            },
            {
                "query": "1017",
                "_id": "12566",
                "_score": 8.0,
                "symbol": "Cdk2",
                "name": "cyclin-dependent kinase 2",
            },
        ],
        "9999": [{"query": "9999", "notfound": True}],
    }

    expected_scopes_by_backend = {
        "biothings": ANNOTATOR_CLIENTS["gene"]["scopes"],
        "elasticsearch": ANNOTATOR_CLIENTS["gene"]["elasticsearch_scopes"],
    }
    for backend, expected_scopes in expected_scopes_by_backend.items():
        assert registry[backend]["gene"].querymany_calls == [
            {
                "query_list": ["1017", "9999"],
                "scopes": expected_scopes,
                "fields": fields,
            }
        ]


@pytest.mark.asyncio
async def test_annotate_curie_backend_parity_for_raw_single_result_with_extra(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    fields = ["chembl.drug_indications"]
    biothings_result = await run_with_backend(
        "biothings",
        "annotate_curie",
        "CHEMBL.COMPOUND:CHEMBL123",
        raw=True,
        fields=fields,
    )
    elasticsearch_result = await run_with_backend(
        "elasticsearch",
        "annotate_curie",
        "CHEMBL.COMPOUND:CHEMBL123",
        raw=True,
        fields=fields,
    )

    assert elasticsearch_result == biothings_result
    chembl_hit = elasticsearch_result["CHEMBL.COMPOUND:CHEMBL123"][0]
    assert chembl_hit["chembl"]["drug_indications"] == [{"mesh_id": "D012345"}]
    assert "atc_classifications" not in chembl_hit
    assert chembl_hit["extra_label"] == "single CHEMBL extra annotation"

    for backend in ("biothings", "elasticsearch"):
        assert registry[backend]["chem"].querymany_calls == [
            {
                "query_list": ["CHEMBL123"],
                "scopes": ANNOTATOR_CLIENTS["chem"]["scopes"],
                "fields": fields,
            }
        ]
        assert registry[backend]["extra"].query_calls == []
        assert registry[backend]["extra"].querymany_calls == [
            {
                "query_list": ["CHEMBL123"],
                "scopes": "_id",
                "fields": "all",
            }
        ]


@pytest.mark.asyncio
async def test_annotate_curie_list_backend_parity_after_transform_and_extra(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    curies = [
        "CHEMBL.COMPOUND:CHEMBL123",
        "PUBCHEM.COMPOUND:2244",
        "PUBCHEM.COMPOUND:0",
        "NCBIGene:1017",
    ]
    biothings_result = await run_with_backend("biothings", "annotate_curie_list", curies)
    elasticsearch_result = await run_with_backend("elasticsearch", "annotate_curie_list", curies)

    assert elasticsearch_result == biothings_result
    assert list(elasticsearch_result) == curies
    assert elasticsearch_result["PUBCHEM.COMPOUND:0"] == [{"query": "0", "notfound": True}]

    chembl_hit = elasticsearch_result["CHEMBL.COMPOUND:CHEMBL123"][0]
    assert chembl_hit["chembl"]["drug_indications"] == [{"mesh_id": "MESH:D012345"}]
    assert chembl_hit["atc_classifications"] == [
        {
            "level1": {"code": "A", "name": "Alimentary tract and metabolism"},
            "level2": {"code": "A01", "name": "Stomatological preparations"},
            "level3": {"code": "A01A", "name": "Stomatological preparations"},
            "level4": {"code": "A01AB", "name": "Antiinfectives and antiseptics for local oral treatment"},
            "level5": {"code": "A01AB02", "name": "Hydrogen peroxide"},
        }
    ]
    assert chembl_hit["extra_label"] == "canonical CHEMBL extra annotation"

    for backend in ("biothings", "elasticsearch"):
        assert registry[backend]["extra"].query_calls == [
            {
                "query": "_exists_:atc.code",
                "fields": "atc.code,atc.name",
                "fetch_all": True,
                "size": None,
                "skip": 0,
            }
        ]
        assert registry[backend]["extra"].querymany_calls == [
            {
                "query_list": [
                    "CHEMBL.COMPOUND:CHEMBL123",
                    "PUBCHEM.COMPOUND:2244",
                    "PUBCHEM.COMPOUND:0",
                ],
                "scopes": "_id",
                "fields": "all",
            }
        ]


@pytest.mark.asyncio
async def test_annotate_curie_list_backend_parity_without_extra_annotations(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    curies = ["CHEMBL.COMPOUND:CHEMBL123", "NCBIGene:1017"]
    biothings_result = await run_with_backend(
        "biothings",
        "annotate_curie_list",
        curies,
        raw=True,
        include_extra=False,
    )
    elasticsearch_result = await run_with_backend(
        "elasticsearch",
        "annotate_curie_list",
        curies,
        raw=True,
        include_extra=False,
    )

    assert elasticsearch_result == biothings_result
    chembl_hit = elasticsearch_result["CHEMBL.COMPOUND:CHEMBL123"][0]
    assert chembl_hit["chembl"]["drug_indications"] == [{"mesh_id": "D012345"}]
    assert "extra_label" not in chembl_hit

    for backend in ("biothings", "elasticsearch"):
        assert registry[backend]["extra"].query_calls == []
        assert registry[backend]["extra"].querymany_calls == []


@pytest.mark.asyncio
async def test_annotate_curie_list_backend_parity_for_duplicate_and_unsupported_curies(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    curies = ["NCBIGene:1017", "NCBIGene:1017", "UNKNOWN:1"]
    biothings_result = await run_with_backend(
        "biothings",
        "annotate_curie_list",
        curies,
        raw=True,
        include_extra=False,
    )
    elasticsearch_result = await run_with_backend(
        "elasticsearch",
        "annotate_curie_list",
        curies,
        raw=True,
        include_extra=False,
    )

    assert elasticsearch_result == biothings_result
    assert list(elasticsearch_result) == ["NCBIGene:1017", "UNKNOWN:1"]
    assert len(elasticsearch_result["NCBIGene:1017"]) == 4
    assert elasticsearch_result["UNKNOWN:1"] == {}

    for backend in ("biothings", "elasticsearch"):
        assert registry[backend]["gene"].querymany_calls == [
            {
                "query_list": ["1017", "1017"],
                "scopes": BIOLINK_PREFIX_to_BioThings["NCBIGene"]["scopes"],
                "fields": ANNOTATOR_CLIENTS["gene"]["fields"],
            }
        ]


@pytest.mark.asyncio
async def test_annotate_curie_backend_parity_for_single_notfound(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    biothings_result = await run_with_backend("biothings", "annotate_curie", "PUBCHEM.COMPOUND:0")
    elasticsearch_result = await run_with_backend("elasticsearch", "annotate_curie", "PUBCHEM.COMPOUND:0")

    assert elasticsearch_result == biothings_result == {
        "PUBCHEM.COMPOUND:0": [{"query": "0", "notfound": True}]
    }

    for backend in ("biothings", "elasticsearch"):
        assert registry[backend]["chem"].querymany_calls == [
            {
                "query_list": ["0"],
                "scopes": ANNOTATOR_CLIENTS["chem"]["scopes"],
                "fields": ANNOTATOR_CLIENTS["chem"]["fields"],
            }
        ]
        assert registry[backend]["extra"].querymany_calls == [
            {
                "query_list": ["0"],
                "scopes": "_id",
                "fields": "all",
            }
        ]


@pytest.mark.asyncio
async def test_annotate_trapi_backend_parity_for_attribute_shape(monkeypatch):
    transformer.atc_cache.clear()
    registry = make_client_registry()
    install_fake_query_clients(monkeypatch, registry)

    trapi_input = {
        "message": {
            "knowledge_graph": {
                "nodes": {
                    "NCBIGene:1017": {"attributes": [{"attribute_type_id": "existing", "value": "keep"}]},
                    "PUBCHEM.COMPOUND:2244": {"attributes": []},
                    "MONDO:0005148": {},
                }
            }
        }
    }

    biothings_result = await run_with_backend("biothings", "annotate_trapi", deepcopy(trapi_input), append=True)
    elasticsearch_result = await run_with_backend(
        "elasticsearch", "annotate_trapi", deepcopy(trapi_input), append=True
    )

    assert elasticsearch_result == biothings_result

    gene_attributes = elasticsearch_result["NCBIGene:1017"]["attributes"]
    assert gene_attributes[0] == {"attribute_type_id": "existing", "value": "keep"}
    assert gene_attributes[1]["attribute_type_id"] == "biothings_annotations"
    assert gene_attributes[1]["value"][0]["symbol"] == "CDK2"

    chem_attributes = elasticsearch_result["PUBCHEM.COMPOUND:2244"]["attributes"]
    assert chem_attributes == [
        {
            "attribute_type_id": "biothings_annotations",
            "value": [
                {
                    "query": "2244",
                    "_id": "PUBCHEM2244",
                    "_score": 34.0,
                    "chembl": {
                        "drug_indications": [{"mesh_id": "MESH:D000001"}],
                        "atc_classifications": "B02BC01",
                    },
                    "atc_classifications": [
                        {
                            "level1": {"code": "B", "name": "Blood and blood forming organs"},
                            "level2": {"code": "B02", "name": "Antihemorrhagics"},
                            "level3": {"code": "B02B", "name": "Vitamin K and other hemostatics"},
                            "level4": {"code": "B02BC", "name": "Local hemostatics"},
                            "level5": {"code": "B02BC01", "name": "Absorbable gelatin sponge"},
                        }
                    ],
                    "extra_label": "canonical PubChem extra annotation",
                }
            ],
        }
    ]

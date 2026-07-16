"""Regression and integrity tests for annotator configuration."""

import tokenize

import pytest

from biothings_annotator.annotator import settings
from biothings_annotator.annotator.annotator import Annotator


EXPECTED_DISEASE_FIELDS = [
    "disease_ontology.doid",
    "mondo.mondo",
    "umls.umls",
    "disease_ontology.name",
    "mondo.label",
    "mondo.definition",
    "disease_ontology.def",
    "mondo.xrefs",
    "disease_ontology.xrefs",
    "mondo.synonym",
    "disease_ontology.synonyms",
]


class FieldFilteringDiseaseClient:
    """Small fake that returns only fields requested by the annotator."""

    def __init__(self):
        self.querymany_calls = []

    async def querymany(self, query_list, scopes, fields):
        query_list = list(query_list)
        fields = list(fields)
        self.querymany_calls.append({"query_list": query_list, "scopes": scopes, "fields": fields})

        hit = {"query": query_list[0]}
        if "mondo.definition" in fields:
            hit.setdefault("mondo", {})["definition"] = "Preferred MONDO definition"
        if "disease_ontology.def" in fields:
            hit.setdefault("disease_ontology", {})["def"] = "Disease Ontology definition"
        return [hit]


@pytest.mark.unit
def test_annotation_default_field_lists_are_well_formed():
    """Default field lists must contain unique, non-empty strings."""
    for node_type, client_settings in settings.ANNOTATOR_CLIENTS.items():
        if "fields" not in client_settings:
            continue

        fields = client_settings["fields"]
        assert isinstance(fields, list), node_type
        assert fields, node_type
        assert all(isinstance(field, str) and field == field.strip() and field for field in fields), node_type
        assert len(fields) == len(set(fields)), node_type


@pytest.mark.unit
def test_settings_do_not_implicitly_concatenate_string_literals():
    """Missing commas between settings strings must fail a deterministic unit test."""
    string_start_token_types = {tokenize.STRING}
    string_end_token_types = {tokenize.STRING}
    if hasattr(tokenize, "FSTRING_START"):
        string_start_token_types.add(tokenize.FSTRING_START)
        string_end_token_types.add(tokenize.FSTRING_END)

    ignored_token_types = {
        tokenize.COMMENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.INDENT,
        tokenize.NL,
    }
    # NEWLINE is deliberately significant: unlike NL inside brackets, it ends
    # an expression, so strings on opposite sides of it are not concatenated.
    previous_token = None
    implicit_concatenations = []

    with tokenize.open(settings.__file__) as source:
        for token in tokenize.generate_tokens(source.readline):
            if token.type in ignored_token_types:
                continue
            if (
                token.type in string_start_token_types
                and previous_token
                and previous_token.type in string_end_token_types
            ):
                implicit_concatenations.append(
                    {
                        "first": (previous_token.start, previous_token.string),
                        "second": (token.start, token.string),
                    }
                )
            previous_token = token

    assert implicit_concatenations == []


@pytest.mark.unit
def test_disease_default_fields_match_the_documented_contract():
    assert settings.ANNOTATOR_CLIENTS["disease"]["fields"] == EXPECTED_DISEASE_FIELDS


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("selected_backend", settings.SUPPORTED_QUERY_BACKENDS)
async def test_default_disease_query_requests_both_definition_sources(monkeypatch, selected_backend):
    """Exercise the default-field path without depending on a live query service."""
    client = FieldFilteringDiseaseClient()

    def get_fake_client(node_type, query_backend, api_host, elasticsearch_connection):
        del api_host, elasticsearch_connection
        assert node_type == "disease"
        assert query_backend == selected_backend
        return client

    monkeypatch.setattr("biothings_annotator.annotator.annotator.get_query_client", get_fake_client)

    result = await Annotator(query_backend=selected_backend).annotate_curie(
        "MONDO:0009693",
        raw=True,
        include_extra=False,
    )

    assert client.querymany_calls == [
        {
            "query_list": ["MONDO:0009693"],
            "scopes": settings.ANNOTATOR_CLIENTS["disease"]["scopes"],
            "fields": EXPECTED_DISEASE_FIELDS,
        }
    ]
    assert result["MONDO:0009693"][0]["mondo"]["definition"] == "Preferred MONDO definition"
    assert result["MONDO:0009693"][0]["disease_ontology"]["def"] == "Disease Ontology definition"

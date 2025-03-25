import argparse
import asyncio
import pathlib
import sqlite3
from typing import AsyncGenerator, Callable, Union

import elasticsearch
from elasticsearch import helpers

import biothings_client

import biothings_annotator
from biothings_client.client.asynchronous import AsyncBiothingClient


async def lookup_gene_curie_id(client: AsyncBiothingClient, connection: sqlite3.Connection) -> None:
    print("Looking up all gene CURIE identifiers")

    async def gene_curie_builder(client: AsyncBiothingClient) -> AsyncGenerator[str, None]:
        gene_generator = await client.query(
            "__all__", fields=["entrezgene", "ensembl.gene", "uniprot.Swiss-Prot"], fetch_all=True
        )

        async for gene_result in gene_generator:
            if gene_result.get("entrezgene", None) is not None:
                yield f"NCBIGene:{gene_result['entrezgene']}"
            elif gene_result.get("ensembl", None) is not None:
                ensembl = gene_result["ensembl"]
                if isinstance(ensembl, dict):
                    if ensembl.get("cid", None) is not None:
                        yield f"ENSEMBL:{ensembl['gene']}"
                elif isinstance(ensembl, list):
                    for ensembl_entry in ensembl:
                        if ensembl_entry.get("gene", None) is not None:
                            yield f"ENSEMBL:{ensembl_entry['gene']}"
            elif gene_result.get("uniprot", None) is not None:
                uniprot = gene_result["uniprot"]
                if uniprot.get("Swiss-Prot", None):
                    yield f"UniProtKB:{uniprot['Swiss-Prot']}"

    await _handle_curie_storage("gene", "gene_curie", gene_curie_builder, client, connection)


async def lookup_chem_curie_id(client: AsyncBiothingClient, connection: sqlite3.Connection) -> None:
    print("Looking up all chem CURIE identifiers")

    async def chem_curie_builder(client: AsyncBiothingClient) -> AsyncGenerator[str, None]:
        chem_generator = await client.query(
            "__all__",
            fields=["pubchem.cid", "chebi.id", "chembl.molecule_chembl_id", "inchikey", "unii.unii"],
            fetch_all=True,
        )
        async for chem_result in chem_generator:
            if chem_result.get("pubchem", None) is not None:
                pubchem = chem_result["pubchem"]
                if isinstance(pubchem, dict):
                    if pubchem.get("cid", None) is not None:
                        yield f"PUBCHEM.COMPOUND:{pubchem['cid']}"
                elif isinstance(pubchem, list):
                    for pub_entry in pubchem:
                        if pub_entry.get("cid", None) is not None:
                            yield f"PUBCHEM.COMPOUND:{pub_entry['cid']}"

            elif chem_result.get("chebi", None) is not None:
                chebi = chem_result["chebi"]
                if isinstance(chebi, dict):
                    if chebi.get("id", None) is not None:
                        yield f"CHEBI:{chebi['id']}"
                elif isinstance(chebi, list):
                    for chebi_entry in chebi:
                        if chebi_entry.get("id", None) is not None:
                            yield f"CHEBI:{chebi_entry['id']}"

            elif chem_result.get("chembl", None) is not None:
                chembl = chem_result["chembl"]
                if isinstance(chembl, dict):
                    if chembl.get("molecule_chembl_id", None) is not None:
                        yield f"CHEMBL.COMPOUND:{chembl['molecule_chembl_id']}"
                elif isinstance(chembl, list):
                    for chembl_entry in chembl:
                        if chembl_entry.get("molecule_chembl_id", None) is not None:
                            yield f"CHEMBL.COMPOUND:{chembl_entry['molecule_chembl_id']}"

            elif chem_result.get("inchikey", None) is not None:
                inchikey = chem_result["inchikey"]
                yield f"INCHIKEY:{inchikey}"

            elif chem_result.get("unii", None) is not None:
                unii = chem_result["unii"]
                if isinstance(unii, dict):
                    if unii.get("unii", None) is not None:
                        yield f"UNII:{unii['unii']}"
                elif isinstance(unii, list):
                    for unii_entry in unii:
                        if unii_entry.get("unii", None) is not None:
                            yield f"UNII:{unii_entry['unii']}"

    await _handle_curie_storage("chem", "chem_curie", chem_curie_builder, client, connection)


async def lookup_disease_curie_id(client: AsyncBiothingClient, connection: sqlite3.Connection) -> None:
    print("Looking up all disease CURIE identifiers")

    async def disease_curie_builder(disease_client: AsyncBiothingClient):
        disease_generator = await disease_client.query(
            "__all__", fields=["disease_ontology.xrefs", "disgenet.xrefs", "mondo.xrefs"], fetch_all=True
        )
        async for disease_result in disease_generator:
            if disease_result.get("disgenet", None) is not None:
                disgenet = disease_result["disgenet"]

                if disgenet.get("xrefs", None) is not None:
                    xrefs = disgenet.get("xrefs", None)
                    if xrefs.get("mondo", None) is not None:
                        yield xrefs["mondo"]
                    elif xrefs.get("doid", None) is not None:
                        yield xrefs["doid"]
                    elif xrefs.get("hp", None) is not None:
                        yield xrefs["hp"]
            elif disease_result.get("disease_ontology", None) is not None:
                disease_ontology = disease_result["disease_ontology"]
                if disease_ontology.get("xrefs", None) is not None:
                    xrefs = disease_ontology.get("xrefs", None)
                    if xrefs.get("mondo", None) is not None:
                        yield xrefs["mondo"]
                    elif xrefs.get("doid", None) is not None:
                        yield xrefs["doid"]
                    elif xrefs.get("hp", None) is not None:
                        yield xrefs["hp"]
            elif disease_result.get("mondo", None) is not None:
                mondo = disease_result["mondo"]
                if mondo.get("xrefs", None) is not None:
                    xrefs = mondo.get("xrefs", None)
                    if xrefs.get("mondo", None) is not None:
                        yield xrefs["mondo"]
                    elif xrefs.get("doid", None) is not None:
                        if isinstance(xrefs["doid"], list):
                            for doid_reference in xrefs["doid"]:
                                yield doid_reference
                        else:
                            yield xrefs["doid"]
                    elif xrefs.get("hp", None) is not None:
                        if isinstance(xrefs["hp"], list):
                            for hp_reference in xrefs["hp"]:
                                yield hp_reference
                        else:
                            yield xrefs["hp"]

    await _handle_curie_storage("disease", "disease_curie", disease_curie_builder, client, connection)


async def _handle_curie_storage(
    data_identifier: str,
    database_table: str,
    builder: Callable,
    client: AsyncBiothingClient,
    connection: sqlite3.Connection,
) -> None:
    """
    Handles the results by calling the asynchronous generator produced
    by the `fetch_all` call for the biothings-client

    Iterates over the data and periodically updating the sqlite3 table
    """
    curie_storage = []
    curie_batch = 0
    async for curie_entry in builder(client):
        curie_storage.append((curie_entry,))
        if len(curie_storage) >= 10000:
            connection.executemany(f"INSERT into {database_table}(curie) values (?)", curie_storage)
            print(f"{data_identifier} batch #{curie_batch} completed | size: {len(curie_storage)}")
            curie_batch += 1
            curie_storage = []

            if curie_batch % 100 == 0:
                connection.commit()
                print(f"curie {data_identifier} database interim commit #{int(curie_batch/100)}")

    if len(curie_storage) > 0:
        connection.executemany(f"INSERT into {database_table}(curie) values (?)", curie_storage)
        print(f"final {data_identifier} batch competed | size: {len(curie_storage)}")

    connection.commit()
    connection.close()


async def bulk_generate_curie_id(gene_filter: bool = False, chem_filter: bool = False, disease_filter: bool = False):
    filter_functions = []
    if gene_filter:
        gene_connection = sqlite3.connect("gene_curie.db")
        gene_table_command = "CREATE TABLE IF NOT EXISTS gene_curie (id INTEGER PRIMARY KEY, curie TEXT);"
        gene_connection.execute(gene_table_command)
        gene_client = biothings_client.get_async_client("gene")

        filter_arguments = {"client": gene_client, "connection": gene_connection}
        filter_functions.append(lookup_gene_curie_id(**filter_arguments))

    if chem_filter:
        chem_connection = sqlite3.connect("chem_curie.db")
        chem_table_command = "CREATE TABLE IF NOT EXISTS chem_curie (id INTEGER PRIMARY KEY, curie TEXT);"
        chem_connection.execute(chem_table_command)
        chem_client = biothings_client.get_async_client("chem")

        filter_arguments = {"client": chem_client, "connection": chem_connection}
        filter_functions.append(lookup_chem_curie_id(**filter_arguments))

    if disease_filter:
        disease_connection = sqlite3.connect("disease_curie.db")
        disease_table_command = "CREATE TABLE IF NOT EXISTS disease_curie (id INTEGER PRIMARY KEY, curie TEXT);"
        disease_connection.execute(disease_table_command)
        disease_client = biothings_client.get_async_client("disease")

        filter_arguments = {"client": disease_client, "connection": disease_connection}
        filter_functions.append(lookup_disease_curie_id(**filter_arguments))

    if len(filter_functions) > 0:
        await asyncio.gather(*filter_functions)


async def generate_index(client: elasticsearch.AsyncElasticsearch, index_name: str) -> None:
    index_configuration = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "mapping": {"total_fields": {"limit": 3000, "ignore_dynamic_beyond_limit": True}},
            },
            "query": {"default_field": "_id,all"},
            "codec": "best_compression",
            "analysis": {
                "analyzer": {
                    # soon deprecated in favor of keyword_lowercase_normalizer
                    "string_lowercase": {
                        "tokenizer": "keyword",
                        "filter": "lowercase",
                    },
                    "whitespace_lowercase": {
                        "tokenizer": "whitespace",
                        "filter": "lowercase",
                    },
                },
                "normalizer": {
                    "keyword_lowercase_normalizer": {
                        "filter": ["lowercase"],
                        "type": "custom",
                        "char_filter": [],
                    },
                },
            },
        },
        "mappings": {
            "dynamic": "true",
        },
    }

    if not (await client.indices.exists(index=index_name)):
        print(f"Creating index: {index_name}")
        await client.indices.create(index=index_name, body=index_configuration)


async def bulk_generate_index() -> None:
    client = elasticsearch.AsyncElasticsearch([{"host": "localhost", "port": 9200, "scheme": "http"}])
    await generate_index(client=client, index_name="gene-annotator-cache")
    await generate_index(client=client, index_name="chem-annotator-cache")
    await generate_index(client=client, index_name="disease-annotator-cache")


async def reset_indices() -> None:
    client = elasticsearch.AsyncElasticsearch([{"host": "localhost", "port": 9200, "scheme": "http"}])
    await client.options(ignore_status=[400, 404]).indices.delete(index="gene-annotator-cache")
    await client.options(ignore_status=[400, 404]).indices.delete(index="chem-annotator-cache")
    await client.options(ignore_status=[400, 404]).indices.delete(index="disease-annotator-cache")


async def seed_cache_index(
    client: elasticsearch.AsyncElasticsearch,
    index_name: str,
    database_file: Union[str, pathlib.Path],
    database_table: str,
    fields: list[str],
) -> None:

    async def curie_database_generator(database: str, table: str) -> list:
        connection = sqlite3.connect(database)
        cursor = connection.cursor()
        chunk_size = 10000
        offset = 0

        while True:
            query = f"SELECT curie FROM {table} LIMIT {chunk_size} OFFSET {offset}"
            cursor.execute(query)
            curie_id = [curie[0].strip() for curie in cursor.fetchall()]

            if curie_id != []:
                annotated_documents = await annotator.annotate_curie_list(
                    curie_list=curie_id, fields=fields, include_extra=True
                )

                for key, documents in annotated_documents.items():
                    yield {key: documents}

                offset += chunk_size
                print(f"Batch offset: {offset}")
            else:
                return

    annotator = biothings_annotator.annotator.Annotator()
    if await client.indices.exists(index=index_name):
        async for document in curie_database_generator(database_file, database_table):
            await client.index(index=index_name, document=document)


async def bulk_populate_index(
    gene_filter: bool = False, chem_filter: bool = False, disease_filter: bool = False
) -> None:
    client = elasticsearch.AsyncElasticsearch([{"host": "localhost", "port": 9200, "scheme": "http"}])

    seeding_functions = []
    if gene_filter:
        gene_fields = biothings_annotator.annotator.settings.ANNOTATOR_CLIENTS["gene"]["fields"]
        gene_seeding = seed_cache_index(
            client=client,
            index_name="gene-annotator-cache",
            database_file="gene_curie.db",
            database_table="gene_curie",
            fields=gene_fields,
        )
        seeding_functions.append(gene_seeding)

    if chem_filter:
        chem_fields = biothings_annotator.annotator.settings.ANNOTATOR_CLIENTS["chem"]["fields"]
        chem_seeding = seed_cache_index(
            client=client,
            index_name="chem-annotator-cache",
            database_file="chem_curie.db",
            database_table="chem_curie",
            fields=chem_fields,
        )
        seeding_functions.append(chem_seeding)

    if disease_filter:
        disease_fields = biothings_annotator.annotator.settings.ANNOTATOR_CLIENTS["disease"]["fields"]
        disease_seeding = seed_cache_index(
            client=client,
            index_name="disease-annotator-cache",
            database_file="disease_curie.db",
            database_table="disease_curie",
            fields=disease_fields,
        )
        seeding_functions.append(disease_seeding)

    if len(seeding_functions) > 0:
        await asyncio.gather(*seeding_functions)


def command_parsing() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--generate-index", dest="genindex", action=argparse.BooleanOptionalAction)
    group.add_argument("--reset-index", dest="resetindex", action=argparse.BooleanOptionalAction)

    subparser = parser.add_subparsers(dest="subcommand")
    filter_id_parser = subparser.add_parser("generate-id")
    filter_id_parser.add_argument("--geneid", action=argparse.BooleanOptionalAction)
    filter_id_parser.add_argument("--diseaseid", action=argparse.BooleanOptionalAction)
    filter_id_parser.add_argument("--chemid", action=argparse.BooleanOptionalAction)

    fill_index_parser = subparser.add_parser("fill-index")
    fill_index_parser.add_argument("--geneid", action=argparse.BooleanOptionalAction)
    fill_index_parser.add_argument("--diseaseid", action=argparse.BooleanOptionalAction)
    fill_index_parser.add_argument("--chemid", action=argparse.BooleanOptionalAction)

    args = parser.parse_args()
    return args


def main():
    arguments = command_parsing()

    if arguments.subcommand is not None:
        if arguments.subcommand == "generate-id":
            asyncio.run(bulk_generate_curie_id(arguments.geneid, arguments.chemid, arguments.diseaseid))
        elif arguments.subcommand == "fill-index":
            asyncio.run(bulk_populate_index(arguments.geneid, arguments.chemid, arguments.diseaseid))
    elif arguments.genindex:
        asyncio.run(bulk_generate_index())
    elif arguments.resetindex:
        asyncio.run(reset_indices())


if __name__ == "__main__":
    main()

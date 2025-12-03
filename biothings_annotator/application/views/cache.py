class CurieCacheView(HTTPMethodView):
    def __init__(self):
        super().__init__()
        application = sanic.Sanic.get_app()

    async def post(self, request: Request):
        """
        openapi:
        ---
        summary: For a list of curie IDs, return the expanded annotation objects
        requestBody:
          content:
            application/json:
              schema:
                properties:
                  ids:
                    description: 'multiple association IDs separated by comma. Note that currently we only take the input ids up to 1000 maximum, the rest will be omitted. Type: string (list). Max: 1000.'
                    type: string
                required:
                - ids
        responses:
          '200':
            description: A list of matching annotation objects
            content:
              application/json:
                schema:
                  type: object
          '400':
            description: A response indicating an improperly formatted query
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    input:
                      type: array
                      items:
                        type: string
                    endpoint:
                      type: string
                    message:
                      type: string
                    supported_nodes:
                      type: array
                      items:
                        type: string
        """
        annotator = Annotator()
        batch_curie_body = request.json

        curie_list = []
        if isinstance(batch_curie_body, dict):
            curie_list = batch_curie_body.get("ids", [])
        elif isinstance(batch_curie_body, list):
            curie_list = batch_curie_body

        if len(curie_list) == 0:
            body_repr = json.dumps(batch_curie_body)
            message = (
                f"No CURIE ID's found in request body. "
                "Expected format: {'ids': ['id0', 'id1', ... 'idN']} || ['id0', 'id1', ... 'idN']. "
                f"Received request body: {body_repr}"
            )
            error_context = {
                "input": batch_curie_body,
                "endpoint": "/cache/",
                "message": message,
                "supported_nodes": InvalidCurieError.annotator_supported_nodes(),
            }
            curie_error_response = sanic.json(error_context, status=400)
            return curie_error_response

        try:
            elasticsearch_client = AsyncElasticsearch(hosts="http://localhost:9200")
            indices = [
                "chem-annotator-cache",
                "gene-annotator-cache",
                "disease-annotator-cache",
            ]

            body = []
            for curie_id in curie_list:
                header = {"index": indices}
                body.append(header)
                query_body = {"query": {"term": {"curie": curie_id}}}
                body.append(query_body)
            multisearch_response = await elasticsearch_client.msearch(body=body)

            cached_annotation = {}
            cache_misses = []

            for search_result, curie_id in zip(multisearch_response["responses"], curie_list):
                search_error = search_result.get("error", None)
                if search_error is not None:
                    cache_misses.append(curie_id)
                else:
                    hits = search_result["hits"]["hits"]
                    if hits:
                        cached_annotation[curie_id] = hits[0]["_source"]["annotation"]
                    else:
                        cache_misses.append(curie_id)

            annotated_cache_misses = await annotator.annotate_curie_list(cache_misses)
            cached_annotation.update(annotated_cache_misses)

            return sanic.json(cached_annotation)

        except InvalidCurieError as curie_err:
            error_context = {
                "input": curie_list,
                "endpoint": "/curie/",
                "message": curie_err.message,
                "supported_nodes": curie_err.supported_biolink_nodes,
            }
            curie_error_response = sanic.json(error_context, status=400)
            return curie_error_response
        except Exception as exc:
            error_context = {
                "input": curie_list,
                "endpoint": "/curie/",
                "message": "Unknown exception occured",
                "exception": repr(exc),
            }
            general_error_response = sanic.json(error_context, status=400)
            return general_error_response

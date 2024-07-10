# biothings annotator

Annotation service for the Translator Project. Originally apart of the 
[pending.api](https://github.com/biothings/pending.api/blob/b7a5a5cb2a890da8563a105e1da1215d7eb09e55/web/handlers/annotator.py),
we've broken it out into it's own service


### Installation


##### environment setup 
```shell
git clone https://github.com/biothings/biothings_annotator
python3 -m venv biothings_annotator
cd biothings_annotator
pip install .
```
##### one-line command installation
```shell
pip install -e git+https://github.com/biothings/biothings_annotator#egg=biothings_annotator
```

### Structure
```shell 
├── biothings_annotator
│   ├── annotator.py <- annotation logic
│   ├── application <- web service logic
│   │   ├── configuration
│   │   ├── views 
│   │   ├── __init__.py
│   │   └── launcher.py
│   ├── biolink.py
│   ├── exceptions.py
│   ├── __init__.py
│   ├── __main__.py <- entrypoint
│   ├── transformer.py
│   └── utility.py
```
`biothings_annotator` is the main module for the python package.
Separated between the annotator logic and web handler logic. 
The annotator logic primarily exists within `annotator.py` and `transformer.py`. Whereas the web server application is defined entirely within `application` directory. 


### Invocation
The `__main__.py` defines the entrypoint to the module for running the `sanic` web server. After
installation run the following to command to start the annotator service:

```
python3 -m biothings_annotator
```

### Docker
We have a Dockerfile and service through docker-compose for the biothings-annotator service. The
Docker file lives in `~/docker/Dockerfile` and defines two build stages. The first pulls down the
repository and creates a wheel for the python package. There are two optional arguments for
controlling the cloning process. 

- `ANNOTATOR_REPO`
- `ANNOTATOR_BRANCH` 

The second build stage sets up the docker environment. It installs packages and then creates the
`annotator` user and home environment. It then creates a virtual environment for the `annotator` user
and installs the wheels generated from the previous builder stage

The entrypoint is set as:

```docker
ENTRYPOINT ["/home/annotator/venv/bin/python", "-m", "biothings_annotator"]
```

Which will call the `__main__.py` entrypoint of the package itself. This should start the sanic web
service for hosting the annotation service


###### Commands

- docker build (default arguments)

```shell
~/biothings_annotator$ docker build ./docker
[+] Building 28.0s (18/18) FINISHED                                                                                                                            docker:default
 => [internal] load build definition from Dockerfile                                                                                                                     0.0s
 => => transferring dockerfile: 1.11kB                                                                                                                                   0.0s
 => [internal] load metadata for docker.io/library/python:3.10-slim                                                                                                      0.6s
 => [internal] load metadata for docker.io/library/python:3.10                                                                                                           0.6s
 => [internal] load .dockerignore                                                                                                                                        0.0s
 => => transferring context: 2B                                                                                                                                          0.0s
 => CACHED [stage-1 1/9] FROM docker.io/library/python:3.10-slim@sha256:3b37199fbc5a730a551909b3efa7b29105c859668b7502451c163f2a4a7ae1ed                                 0.0s
 => [builder 1/4] FROM docker.io/library/python:3.10@sha256:506eee363017f0b9c7f06f4839e7db90d1001094882e8cff08c8261ba2e05be2                                             0.0s
 => [stage-1 2/9] RUN apt update -q -y && apt install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*                                                     10.4s
 => CACHED [builder 2/4] WORKDIR /build/annotator                                                                                                                        0.0s
 => [builder 3/4] RUN git clone -b main --recursive https://github.com/biothings/biothings_annotator.git .                                                               1.0s
 => [builder 4/4] RUN pip wheel --wheel-dir=/build/wheels /build/annotator                                                                                               6.3s
 => [stage-1 3/9] RUN apt-get update -y && apt-get install vim -y && apt-get install sudo -y && apt-get install telnet -y                                               11.0s
 => [stage-1 4/9] RUN useradd -m annotator && usermod -aG sudo annotator                                                                                                 0.4s
 => [stage-1 5/9] RUN python -m venv /home/annotator/venv                                                                                                                2.9s
 => [stage-1 6/9] COPY --from=builder --chown=annotator:annotator /build/wheels /home/annotator/wheels                                                                   0.1s
 => [stage-1 7/9] RUN /home/annotator/venv/bin/pip install /home/annotator/wheels/*.whl && rm -rf /home/annotator/wheels                                                 2.3s
 => [stage-1 8/9] COPY --from=builder --chown=annotator:annotator /build/annotator /home/annotator/biothings_annotator                                                   0.0s
 => [stage-1 9/9] WORKDIR /home/annotator/                                                                                                                               0.0s
 => exporting to image                                                                                                                                                   0.2s
 => => exporting layers                                                                                                                                                  0.2s
 => => writing image sha256:11c4e8ad86724c8c223b7f07ade148c4701c43acff5d73fa26e06e139a230019                                                                             0.0s
 ```

- docker build (with arguments)

```shell
~/biothings_annotator$ docker build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main ./docker/
[+] Building 25.9s (18/18) FINISHED                                                                                                                            docker:default
 => [internal] load build definition from Dockerfile                                                                                                                     0.0s
 => => transferring dockerfile: 1.11kB                                                                                                                                   0.0s
 => [internal] load metadata for docker.io/library/python:3.10-slim                                                                                                      0.3s
 => [internal] load metadata for docker.io/library/python:3.10                                                                                                           0.5s
 => [internal] load .dockerignore                                                                                                                                        0.0s
 => => transferring context: 2B                                                                                                                                          0.0s
 => CACHED [stage-1 1/9] FROM docker.io/library/python:3.10-slim@sha256:3b37199fbc5a730a551909b3efa7b29105c859668b7502451c163f2a4a7ae1ed                                 0.0s
 => [builder 1/4] FROM docker.io/library/python:3.10@sha256:506eee363017f0b9c7f06f4839e7db90d1001094882e8cff08c8261ba2e05be2                                             0.0s
 => CACHED [builder 2/4] WORKDIR /build/annotator                                                                                                                        0.0s
 => [stage-1 2/9] RUN apt update -q -y && apt install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*                                                      8.7s
 => [builder 3/4] RUN git clone -b main --recursive https://github.com/biothings/biothings_annotator.git .                                                               1.0s
 => [builder 4/4] RUN pip wheel --wheel-dir=/build/wheels /build/annotator                                                                                               6.6s
 => [stage-1 3/9] RUN apt-get update -y && apt-get install vim -y && apt-get install sudo -y && apt-get install telnet -y                                               10.4s
 => [stage-1 4/9] RUN useradd -m annotator && usermod -aG sudo annotator                                                                                                 0.5s
 => [stage-1 5/9] RUN python -m venv /home/annotator/venv                                                                                                                2.9s
 => [stage-1 6/9] COPY --from=builder --chown=annotator:annotator /build/wheels /home/annotator/wheels                                                                   0.0s
 => [stage-1 7/9] RUN /home/annotator/venv/bin/pip install /home/annotator/wheels/*.whl && rm -rf /home/annotator/wheels                                                 2.4s
 => [stage-1 8/9] COPY --from=builder --chown=annotator:annotator /build/annotator /home/annotator/biothings_annotator                                                   0.1s
 => [stage-1 9/9] WORKDIR /home/annotator/                                                                                                                               0.1s
 => exporting to image                                                                                                                                                   0.2s
 => => exporting layers                                                                                                                                                  0.2s
 => => writing image sha256:dee96b398b55ba335494490eddfd7735e3fc6cced1ba971a7d2509a64809cc24                                                                             0.0s
```

- docker compose build (same output as above)

```shell
~/biothings_annotator$ docker compose build 
~/biothings_annotator$ docker compose build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main
```

- docker run 

```shell
~/biothings_annotator$ docker run biothings_annotator-annotator

docker run biothings_annotator-annotator
INFO:sanic-application:global sanic configuration:
 {
    "network": {
        "host": "0.0.0.0",
        "port": 9999
    },
    "application": {
        "settings": {}
    }
}
INFO:sanic-application:generated sanic application from loader: <Sanic TEST-SANIC>
DEBUG:sanic.root:

                 Sanic
         Build Fast. Run Fast.


INFO:sanic.root:Sanic v24.6.0
INFO:sanic.root:Goin' Fast @ http://127.0.0.1:9999
INFO:sanic.root:app: TEST-SANIC
Main  21:39:25 DEBUG:

                 Sanic
         Build Fast. Run Fast.


Main  21:39:25 INFO: Sanic v24.6.0
Main  21:39:25 INFO: Goin' Fast @ http://127.0.0.1:9999
Main  21:39:25 INFO: app: TEST-SANIC
Main  21:39:25 INFO: mode: debug, single worker
Main  21:39:25 INFO: server: sanic, HTTP/1.1
INFO:sanic.root:mode: debug, single worker
INFO:sanic.root:server: sanic, HTTP/1.1
INFO:sanic.root:python: 3.10.14
INFO:sanic.root:platform: Linux-6.5.0-1025-oem-x86_64-with-glibc2.36
INFO:sanic.root:auto-reload: enabled
Main  21:39:25 INFO: python: 3.10.14
Main  21:39:25 INFO: platform: Linux-6.5.0-1025-oem-x86_64-with-glibc2.36
Main  21:39:25 INFO: auto-reload: enabled
Main  21:39:25 INFO: packages: sanic-routing==23.12.0
INFO:sanic.root:packages: sanic-routing==23.12.0
Main  21:39:25 DEBUG: Creating multiprocessing context using 'spawn'
DEBUG:sanic.root:Creating multiprocessing context using 'spawn'
Main  21:39:25 DEBUG: Starting a process: Sanic-Server-0-0
DEBUG:sanic.root:Starting a process: Sanic-Server-0-0
DEBUG:sanic.root:Starting a process: Sanic-Reloader-0
Main  21:39:25 DEBUG: Starting a process: Sanic-Reloader-0
DEBUG:sanic.root:Process ack: Sanic-Server-0-0 [15]
Srv 0 21:39:26 DEBUG: Process ack: Sanic-Server-0-0 [15]
Srv 0 21:39:26 INFO: Starting worker [15]
INFO:sanic.server:Starting worker [15]
```

- docker compose up 

```shell
biothings) jschaff@tsri-ubuntu:~/workspace/biothings/biothings_annotator$ docker compose up
[+] Running 2/0
 ✔ Container biothings-annotator                                        Recreated                                                     0.0s
 ! annotator Published ports are discarded when using host network mode                                                               0.0s
Attaching to biothings-annotator
biothings-annotator  | INFO:sanic-application:global sanic configuration:
biothings-annotator  |  {
biothings-annotator  |     "network": {
biothings-annotator  |         "host": "0.0.0.0",
biothings-annotator  |         "port": 9999
biothings-annotator  |     },
biothings-annotator  |     "application": {
biothings-annotator  |         "settings": {}
biothings-annotator  |     }
biothings-annotator  | }
biothings-annotator  | INFO:sanic-application:generated sanic application from loader: <Sanic TEST-SANIC>
biothings-annotator  | DEBUG:sanic.root:
biothings-annotator  |
biothings-annotator  |                  Sanic
biothings-annotator  |          Build Fast. Run Fast.
biothings-annotator  |
biothings-annotator  |
biothings-annotator  | INFO:sanic.root:Sanic v24.6.0
biothings-annotator  | INFO:sanic.root:Goin' Fast @ http://127.0.0.1:9999
biothings-annotator  | INFO:sanic.root:app: TEST-SANIC
biothings-annotator  | INFO:sanic.root:mode: debug, single worker
biothings-annotator  | INFO:sanic.root:server: sanic, HTTP/1.1
biothings-annotator  | INFO:sanic.root:python: 3.10.14
biothings-annotator  | Main  21:41:22 DEBUG:
biothings-annotator  |
biothings-annotator  |                  Sanic
biothings-annotator  |          Build Fast. Run Fast.
biothings-annotator  |
biothings-annotator  |
biothings-annotator  | Main  21:41:22 INFO: Sanic v24.6.0
biothings-annotator  | Main  21:41:22 INFO: Goin' Fast @ http://127.0.0.1:9999
biothings-annotator  | Main  21:41:22 INFO: app: TEST-SANIC
biothings-annotator  | Main  21:41:22 INFO: mode: debug, single worker
biothings-annotator  | Main  21:41:22 INFO: server: sanic, HTTP/1.1
biothings-annotator  | Main  21:41:22 INFO: python: 3.10.14
biothings-annotator  | Main  21:41:22 INFO: platform: Linux-6.5.0-1025-oem-x86_64-with-glibc2.36
biothings-annotator  | Main  21:41:22 INFO: auto-reload: enabled
biothings-annotator  | Main  21:41:22 INFO: packages: sanic-routing==23.12.0
biothings-annotator  | INFO:sanic.root:platform: Linux-6.5.0-1025-oem-x86_64-with-glibc2.36
biothings-annotator  | INFO:sanic.root:auto-reload: enabled
biothings-annotator  | INFO:sanic.root:packages: sanic-routing==23.12.0
biothings-annotator  | Main  21:41:22 DEBUG: Creating multiprocessing context using 'spawn'
biothings-annotator  | DEBUG:sanic.root:Creating multiprocessing context using 'spawn'
biothings-annotator  | Main  21:41:22 DEBUG: Starting a process: Sanic-Server-0-0
biothings-annotator  | DEBUG:sanic.root:Starting a process: Sanic-Server-0-0
biothings-annotator  | DEBUG:sanic.root:Starting a process: Sanic-Reloader-0
biothings-annotator  | Main  21:41:22 DEBUG: Starting a process: Sanic-Reloader-0
biothings-annotator  | Srv 0 21:41:23 DEBUG: Process ack: Sanic-Server-0-0 [15]
biothings-annotator  | DEBUG:sanic.root:Process ack: Sanic-Server-0-0 [15]
biothings-annotator  | INFO:sanic.server:Starting worker [15]
biothings-annotator  | Srv 0 21:41:23 INFO: Starting worker [15]
```


### Tests
The tests are implemented with `pytest` in mind.
To install the test dependencies `pip install .[tests]`. 

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

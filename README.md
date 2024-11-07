# biothings annotator

Annotation service for the Translator Project. Originally apart of the 
[pending.api](https://github.com/biothings/pending.api/blob/b7a5a5cb2a890da8563a105e1da1215d7eb09e55/web/handlers/annotator.py),
we've broken it out into it's own service


### Installation


##### Environment Setup 
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
biothings_annotator
├── annotator <- annotation backend logic
└── application <- web service logic
    ├── cli
    ├── configuration
    ├── exceptions
    ├── middleware
    └── views
```

`biothings_annotator` is as a package is separated into the annotator logic and web handler logic. 
The annotator logic primarily exists within `annotator/annotator.py` and `annotator/transformer.py`.
Whereas the web server application is defined entirely within `application` directory. 


### Command-line Interface
The `__main__.py` defines the entrypoint to the module for running the `sanic` web server. After
installation run the following to command to start the annotator service:

```shell
python3 -m biothings_annotator
```

###### Command-line Implementation
The `__main__.py` file points to the application module where it will run the `main` function within
the launcher. The majority of our implementation exists within the
`biothings_annotator/application/cli` module. We store the main command line handling logic in
`cli/interface.py` with argument definitions and other argument handling in `cli/arguments.py`. We
wanted to maintain the same command line interface as sanic. `sanic` has a `cli`
module where it defines the `SanicCLI`class for handling their command-line implementation. However
we also have additional arguments we want to support. So we override the `SanicCLI` to acquire the
original parser handlers. The command-line steps are then divided in three steps shown below.

```python
# Entrypoint

cli = AnnotatorCLI()
cli.attach()
cli.parse()
cli.run()
```

The `attach` method aggregates all of the `ArgumentParser` instances stored in what `sanic` 
defines as `Group` objects. In order to add our custom arguments we define our own implementations
of the `Group` argument parsers to be called during the `attach` method. 

The `parse` method then builds the parsers from `Group` objects. While we want to support the same
interface as `sanic`, we do limit some of the options. The main limit is the `target` option which
points to a module or factory for building the `AppLoader` instance. We hard-set that and a couple
other options so that we cannot accidently change the path we point to for building the web server
implementation. Our factory method for generating the `sanic.Sanic` application instance is defined
with `cli/target.py`.

```python

# Original AppLoader instance
app_loader = AppLoader(
    self.args.target, self.args.factory, self.args.simple, self.args
)

# biothings-annotator AppLoader instance
application_loader = AppLoader(
    module_input=self.args.target, # hard-coded to ""
    as_factory=self.args.factory, # hard-coded to False
    as_simple=self.args.simple, # hard-coded to False
    args=self.args,
    factory=functools.partial(build_application, self.server_configuration),
)

# AppLoader definition
class AppLoader:
    """
    A helper to load application instances.
    Args:
        module_input (str): The module to load the application from.
        as_factory (bool): Whether the application is a factory.
        as_simple (bool): Whether the application is a simple server.
        args (Any): Arguments to pass to the application factory.
        factory (Callable[[], SanicApp]): A callable that returns a Sanic application instance.
    """

    def __init__(
        self,
        module_input: str = "",
        as_factory: bool = False,
        as_simple: bool = False,
        args: Any = None,
        factory: Optional[Callable[[], SanicApp]] = None,
    ) -> None:
```

The `run` method builds the `AppLoader` instance and the runtime arguments builder method. The
default command line arguments are shown below:

```python
default_parameters = {
    "access_log": None,
    "auto_tls": False,
    "coffee": False,
    "debug": False,
    "fast": False,
    "host": None,
    "motd": True,
    "noisy_exceptions": None,
    "port": None,
    "single_process": False,
    "ssl": None,
    "unix": "",
    "verbosity": 0,
    "workers": 1,
}
```

Some of these arguments are hard-set by the configuration file defaults and cannot be changed at the
command-line unless the configuration file is modified. 

##### Examples

```shell
python3 -m biothings_annotator --host "172.84.29.248"
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 --workers 12 
python3 -m biothings_annotator --host "172.84.29.248" --port 9384 --workers 12 --debug
```


### Builds

```shell
docker
├── configuration
│   ├── Caddyfile
│   └── supervisord.conf
└── Dockerfile
```

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
ENTRYPOINT ["supervisord"]
CMD ["-c", "/etc/supervisor/supervisord.conf"]
```

This leverages supervisord to launch to different services. The first is the annotator web server

```shell
[program:python_app]
command=/home/annotator/venv/bin/python -m biothings_annotator --conf=/home/annotator/configuration/default.json
```

This command will call the `__main__.py` entrypoint of the package itself. This should start the sanic web
service for hosting the annotation service. For configuration of the service itself, modify the
configuration found under `biothings_annotator/application/configuration/sanic.json`.

The second service launched is caddy. We use caddy in this case as a reverse proxy.

```shell
[program:caddy]
command=caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
```

The default port for the web server is `9001`, and the caddy proxy forwards to that upstream web server via port
`9000` for deployment purposes. The main purposes at the moment for caddy are for compression and
potential future usage as a load balancer


###### docker build

- default 
    - `~/biothings_annotator$ docker build ./docker`
    - `~/biothings_annotator$ docker build . -f docker/Dockerfile`

- build arguments
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_BRANCH=main ./docker/`
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git ./docker/`
    - `~/biothings_annotator$ docker build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main ./docker/`

- tag
    - `~/biothings_annotator$ docker build ./docker/ --tag=annotator`

- without caching
    - `~/biothings_annotator$ docker build ./docker/ --no-cache`


###### docker compose build
- default 
    - `~/biothings_annotator$ docker compose build`

- build arguments
    - `~/biothings_annotator$ docker compose build --build-arg ANNOTATOR_REPO=https://github.com/biothings/biothings_annotator.git --build-arg ANNOTATOR_BRANCH=main ./docker/`


###### docker run
    - `~/biothings_annotator$ docker run <annotator-image-name>`


###### docker compose up 
    - `~/biothings_annotator$ docker run <annotator-image-name>`



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

...
```

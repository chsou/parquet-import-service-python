# Copyright (c) 2024 Cumulocity GmbH

import glob
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime
import re

import dotenv
from dunamai import Version
from invoke import task

import microservice_util as ms_util


def read_file(fn):
    """Read file contents."""
    with open(fn, 'rt', encoding='utf-8') as fp:
        return fp.readline().strip()


def write_file(fn, text):
    """Write file contents."""
    with open(fn, 'wt', encoding='utf-8') as fp:
        return fp.write(text)


MICROSERVICE_NAME = read_file('MICROSERVICE_NAME')
ISOLATION = read_file('ISOLATION')
PROVIDER = read_file('PROVIDER')

logger = logging.getLogger()


def init_logging(level: str):
    """Setup local logging configuration."""
    level = {
        'd': logging.DEBUG,
        'i': logging.INFO,
        'w': logging.WARNING,
        'e': logging.ERROR,
    }[level[0]]

    logger.setLevel(level)

    std_formatter = logging.Formatter("%(message)s")
    std_handler = logging.StreamHandler(sys.stdout)
    std_handler.setLevel(logging.DEBUG)
    std_handler.setFormatter(std_formatter)
    std_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    logger.addHandler(std_handler)

    err_formatter = logging.Formatter("%(levelname)s: %(message)s")
    err_handler = logging.StreamHandler(sys.stdout)
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(err_formatter)
    logger.addHandler(err_handler)


def limit_string(string: str, length: int = 75):
    """Truncate/abbreviate long strings."""
    if len(string) < length:
        return string
    return f"{string[:length-11]} ... {string[-5:]}"


def assert_name(name):
    """Verify that a given (microservice) name is valid according to Cumulocity
    naming standards."""
    if not re.match(r'[a-zA-Z]+[a-zA-Z0-9\-]+', name):
        logger.error(f"Provided name ({name}) does not conform to Cumulocity naming standards.")
        exit(2)


def assert_isolation(isolation):
    """Verify that a given (microservice) isolation is defined."""
    if isolation not in ['MULTI_TENANT', 'PER_TENANT']:
        logger.error(f"Provided isolation level ({isolation}) is invalid.")
        exit(2)


def resolve_version():
    """Resolve a formatted version string based on the latest VCS tag.

    The VCS tag must have a look like `vx.y.z`, the formatted version string
    will be `<base>[-c<num commits>][-r<date><time>]`. The number of commits
    will be omitted if the tag is on the current HEAD. The date and time will
    be omitted if the local copy is not dirty (i.e. everything is committed).
    """
    version = Version.from_any_vcs()
    result = version.base
    if version.distance:
        result = result + '-c' + str(version.distance).rjust(2, '0')
    if version.dirty:
        result = result + datetime.now().strftime('-r%y%m%d%H%M')
    return result


@contextmanager
def load_env():
    """Load Cumulocity environment variables.

    This function will first check, whether environment variables are already
    present within the environment (e.g. have been loaded by the c8y-go-cli)
    and use them if available. Alternatively, it will load a .env file
    if it exists.
    """
    c8y_vars = {k: v for k, v in os.environ.items() if k.startswith('C8Y_')}
    if c8y_vars:
        logger.info("Found Cumulocity session variables in environment.")
        for k, v in c8y_vars.items():
            logger.debug(limit_string(f"  {k}={v}"))
    if os.path.isfile('.env'):
        if c8y_vars:
            logging.warning("Local .env file is ignored because environment variables are defined.")
        else:
            logging.info("Local .env file found.")
            dotenv.load_dotenv()

    yield os.environ


@task(help={
    'name': "New name of the microservice. Needs to conform to Cumulocity"
            " naming rules.",
    'isolation': "New isolation level. Needs to be one of MULTI_TENANT or"
            " PER¶_TENANT.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def init(_, name=None, isolation=None, loglevel="info"):
    """Init the microservice project with name and isolation level.

    This sets a default microservice name as it should be represented in
    Cumulocity as well as the isolation level.
    """
    init_logging(loglevel)
    # Check name pattern (start with a letter followed by any number of letters, digits and dashes, no underscores)
    name = name or input(f"Enter new name for microservice ({MICROSERVICE_NAME}): ") or MICROSERVICE_NAME
    assert_name(name)
    isolation = isolation or input(f"Enter microservice isolation level ({ISOLATION}): ") or ISOLATION
    assert_isolation(isolation)
    write_file('MICROSERVICE_NAME', name)
    logger.info(f'New microservice name written: {name}')
    write_file('ISOLATION', isolation)
    logger.info(f'New isolation level written: {isolation}')


@task
def show_version(_):
    """Print the module version.

    This version string is inferred from the last Git tag. A tagged HEAD
    should resolve to a clean semver (vX.Y.Z) version string.
    """
    init_logging('info')
    logger.info(resolve_version())


@task(help={
    'scope': "Which source directory to check (e.g. 'main'). Default: 'all'."
})
def lint(c, scope='all'):
    """Run PyLint."""
    if scope == 'all':
        paths = " ".join([n for n in glob.glob('src/*/') if os.path.isdir(n)])
    else:
        paths = f'src/{scope}/'
    c.run(f'pylint {paths}')


@task(help={
    'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
    "version": "Microservice version. If not provided, defaults to a "
               "generated value based on the last Git tag.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def build(c, version=None, name=MICROSERVICE_NAME, loglevel="info"):
    """Build a Cumulocity microservice binary for upload.

    This will build a ready to deploy Cumulocity microservice from the
    sources.
    """
    init_logging(loglevel)
    assert_name(name)
    assert_isolation(ISOLATION)
    version = version or resolve_version()
    c.run(f'./build.sh -n {name} -v {version} -i {ISOLATION} -p "{PROVIDER}"')


@task(help={
    'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def register(_, name=MICROSERVICE_NAME, loglevel='info'):
    """Register a microservice at Cumulocity."""
    init_logging(loglevel)
    with load_env():
        ms_util.register_microservice(name)


@task(help={
    'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def deregister(_, name=MICROSERVICE_NAME, loglevel='info'):
    """Deregister a microservice from Cumulocity."""
    init_logging(loglevel)
    with load_env():
        ms_util.unregister_microservice(name)


@task(
    help={
        'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
        "version": "Microservice version. If not provided, defaults to a "
                   "generated value based on the last Git tag.",
        'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def upload(c, version=None, name=MICROSERVICE_NAME, loglevel='info'):
    """Build, and upload microservice to Cumulocity."""
    init_logging(loglevel)
    build(c, version=version, name=name, loglevel=loglevel)
    with load_env():
        ms_util.register_microservice(name)
        ms_util.upload_microservice(name, f"dist/{name}.zip")



@task
def run(c):
    c.run('python src/main/main.py')


def get_env(name, isolation):
    """Obtain the microservice's environment variables."""
    # TODO: Do something if not registered, yet
    if isolation == 'PER_TENANT':
        return ms_util.get_service_credentials(name)
    elif isolation == 'MULTI_TENANT':
        return ms_util.get_bootstrap_credentials(name)

    raise ValueError(f"Unknown isolation: '{isolation}'")


@task(help={
    'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
    'isolation': f"ISOLATION mode. Defaults to '{ISOLATION}'.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def print_env(_, name=MICROSERVICE_NAME, isolation=ISOLATION, loglevel='info'):
    """Read and print credentials of registered microservice."""
    init_logging(loglevel)
    _, tenant, user, password = get_env(name, isolation)
    logging.info(
        f"Tenant:    {tenant}\n"
        f"Username:  {user}\n"
        f"Password:  {password}"
    )


@task(help={
    'name': f"Microservice name. Defaults to '{MICROSERVICE_NAME}'.",
    'isolation': f"ISOLATION mode. Defaults to '{ISOLATION}'.",
    'file': "Force custom environment variables file name; By default .env-ms is used.",
    'loglevel': "Log level. Can be one of: debug, info, warning, error. Defaults to 'info'.",
})
def write_env(_, name=MICROSERVICE_NAME, isolation=ISOLATION, file=".env-ms", loglevel='info'):
    """Create a .env file to hold the credentials of the microservice
    registered at Cumulocity."""
    init_logging(loglevel)
    with load_env():
        base_url, tenant, user, password = get_env(name, isolation)
        logger.info(f"Writing microservice environment variables to file: {file}")
        with open(file, 'w', encoding='UTF-8') as f:
            bootstrap = 'BOOTSTRAP_' if ISOLATION == 'MULTI_TENANT' else ''
            f.write(f'C8Y_BASEURL={base_url}\n'
                    f'C8Y_{bootstrap}TENANT={tenant}\n'
                    f'C8Y_{bootstrap}USER={user}\n'
                    f'C8Y_{bootstrap}PASSWORD={password}\n')


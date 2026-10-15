# Copyright (c) 2024 Cumulocity GmbH

import json
import logging

from c8y_api import CumulocityRestApi
from dotenv import load_dotenv

from c8y_api.app import SimpleCumulocityApp
from c8y_api.model import Application

logger = logging.getLogger()


def register_microservice(name: str):
    """ (Re-) register a microservice at Cumulocity.

    The Cumulocity connection information is taken from the environment
    .env file located in the working directory.

    Args:
        name (str):  The application name to use
    """
    logger.info(f"Registering microservice '{name}'.")

    load_dotenv()
    c8y = SimpleCumulocityApp()

    apps = c8y.applications.get_all(name=name)

    # parse microservice manifest
    with open('./src/cumulocity.json') as fp:
        manifest_json = json.load(fp)
    required_roles = manifest_json['requiredRoles']
    logger.info(f"Microservice roles: {', '.join(required_roles)}.")

    # (2) update already existing
    if apps:
        app = apps[0]
        if set(app.required_roles) == set(required_roles):
            logger.info(f"Microservice application '{name}' (ID {app.id}) already up to date.")
        else:
            app.required_roles = required_roles
            app.update()
            logger.info(f"Microservice application '{name}' (ID {app.id}) updated.")
        return

    # (3) create new applications stub
    app = Application(
        c8y,
        name=name,
        key=f'{name}-key',
        type=Application.MICROSERVICE_TYPE,
        availability=Application.PRIVATE_AVAILABILITY,
        required_roles=required_roles
    ).create()

    # Subscribe to newly created microservice
    subscription_json = {'application': {'self': f'{c8y.base_url}/application/applications/{app.id}'}}
    c8y.post(f'/tenant/tenants/{c8y.tenant_id}/applications', json=subscription_json)

    logger.info(f"Microservice application '{name}' (ID {app.id}) created. Tenant '{c8y.tenant_id}' subscribed.")


def unregister_microservice(name: str):
    """ Unregister a microservice from Cumulocity.

    The Cumulocity connection information is taken from the environment
    .env file located in the working directory.

    Args:
        name (str):  The name of the application to use

    Throws:
        LookupError  if a corresponding application cannot be found.
    """
    load_dotenv()

    try:
        c8y = SimpleCumulocityApp()
        # read applications by name, will throw IndexError if there is none
        app = c8y.applications.get_all(name=name)[0]
        # delete by ID
        app.delete()
    except IndexError as e:
        raise LookupError(f"Cannot retrieve information for an application named '{name}'.") from e

    print(f"Microservice application '{name}' (ID {app.id}) deleted.")


def upload_microservice(name: str, file: str):
    """ Update a microservice at Cumulocity.

    The Cumulocity connection information is taken from the environment
    .env file located in the working directory.

    Args:
        name (str):  The name of the application to use
        file (str):  The filename of the packed (.zip) application image
    """
    load_dotenv()
    c8y = SimpleCumulocityApp()
    try:
        app = c8y.applications.get_all(name=name)[0]
        logger.info(f"Uploading binary for microservice '{name}' (ID {app.id}) ...")
        c8y.applications.upload_attachment(app.id, file)
        logger.info("Microservice binary uploaded successfully.")

    except IndexError as e:
        raise RuntimeError(f"Cannot retrieve information for an application named '{name}'.") from e


def get_bootstrap_credentials(name: str) -> (str, str):
    """ Get the bootstrap user credentials of a registered microservice.

    The Cumulocity connection information is taken from environment files
    (.env and .env-SAMPLE-NAME) located in the working directory.

    Note: this function is only applicable to _multi-tenant_ microservices.

    Args:
        name (str):  The name of the application to use

    Returns:
        A tuple (baseurl, tenant_id, username, password) for the credentials.

    Throws:
        LookupError  if a corresponding application cannot be found.
    """
    load_dotenv()

    c8y = SimpleCumulocityApp()
    try:
        # read applications by name, will throw IndexError if there is none
        app = c8y.applications.get_all(name=name)[0]
    except IndexError as e:
        raise LookupError(f"Cannot retrieve information for an application named '{name}'.") from e

    # read bootstrap user details
    user_json = c8y.get(f'/application/applications/{app.id}/bootstrapUser')
    return c8y.base_url, user_json['tenant'], user_json['name'], user_json['password']


def get_service_credentials(name: str) -> (str, str):
    """ Get the service user credentials of a registered microservice.

    The Cumulocity connection information is taken from environment files
    (.env and .env-SAMPLE-NAME) located in the working directory.

    Note: this function is only applicable to _per tenant_ microservices.

    Args:
        name (str):  The name of the application to use

    Returns:
        A tuple (baseurl, tenant_id, username, password) for the credentials.

    Throws:
        LookupError  if a corresponding application cannot be found.
    """
    load_dotenv()
    c8y = SimpleCumulocityApp()

    try:
        # read bootstrap user
        _, tenant_id, username, password = get_bootstrap_credentials(name)
        # read subscriptions, there should only be one for simple microservices
        bootstrap_c8y = CumulocityRestApi(base_url=c8y.base_url, tenant_id=tenant_id, username=username, password=password)
        subscriptions_json = bootstrap_c8y.get('/application/currentApplication/subscriptions')
        service_user = subscriptions_json['users'][0]
        return c8y.base_url, service_user['tenant'], service_user['name'], service_user['password']

    except IndexError as e:
        raise LookupError(f"Cannot retrieve information for an application named '{name}'.") from e

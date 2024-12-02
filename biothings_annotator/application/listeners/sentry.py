"""
Listener for configuring the sentry support for the
sanic web-app associated with the annotator service
"""

import sanic

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.sanic import SanicIntegration


async def initialize_sentry(application_instance: sanic.Sanic) -> None:
    """
    Listener for initializing our sentry logging

    Set the sample rate for transactions
    https://docs.sentry.io/platforms/python/configuration/options/#traces-sample-rate

    Set the profiles sample rate for transactions
    https://docs.sentry.io/platforms/python/profiling/
    """
    # https://docs.sentry.io/platforms/python/integrations/asyncio/
    async_integration = AsyncioIntegration()

    # https://docs.sentry.io/platforms/python/integrations/sanic/
    sanic_integration = SanicIntegration(
        # Configure the Sanic integration so that we generate
        # transactions for all HTTP status codes, including 404
        unsampled_statuses=None,
    )
    sentry_configuration = application_instance.config.get("sentry", {})
    sentry_key = sentry_configuration.get("SENTRY_CLIENT_KEY", "")
    sentry_sdk.init(
        dsn=sentry_key,
        traces_sample_rate=0.20,
        profiles_sample_rate=0.20,
        integrations=[async_integration, sanic_integration],
    )

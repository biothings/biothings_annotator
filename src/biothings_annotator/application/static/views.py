from sanic import file
from sanic.views import HTTPMethodView
from sanic.request import Request

from biothings_annotator.application.structure import DOCKER_WEB_APP_DIRECTORY, WEB_APP_DIRECTORY


class StaticFrontendView(HTTPMethodView):

    async def get(self, _: Request) -> file:
        """Loads the main index for our openapi swagger ui.

        The local file must be relative given we have both local
        development and docker development

        The WEB_APP_DIRECTORY is relative to the webapp directory
        in the biothings-annotator repository

        The DOCKER_WEB_APP_DIRECTORY is /webapp at the root of the
        docker container
        """

        if DOCKER_WEB_APP_DIRECTORY.exists():
            html_index_file = DOCKER_WEB_APP_DIRECTORY.joinpath("index.html")
        else:
            html_index_file = WEB_APP_DIRECTORY.joinpath("index.html")
        return await file(html_index_file)

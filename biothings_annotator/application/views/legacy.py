import openapi
import sanic
from sanic.views import HTTPMethodView
from sanic.request import Request


# --- Legacy Redirects ---
# The /annotator endpoint has been deprecated so we setup these redirects:
# GET /annotator/<CURIE_ID> -> /curie/<CURIE_ID> (Singular CURIE ID)
# POST /annotator/ -> /trapi/
class CurieLegacyView(HTTPMethodView):
    @openapi.deprecated()
    async def get(self, request: Request, curie: str):
        redirect_response = sanic.response.redirect(f"/curie/{curie}", status=302)
        return redirect_response


class TrapiLegacyView(HTTPMethodView):
    @openapi.deprecated()
    async def post(self, request: Request):
        redirect_response = sanic.response.redirect("/trapi/", status=302)
        return redirect_response

"""Same-origin Swagger with explicit human and integration authorization."""
from pathlib import Path
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ASSETS = Path(__file__).with_suffix('')


def install(app):
    app.mount('/docs/assets', StaticFiles(directory=ASSETS), name='swagger_assets')

    @app.get('/docs/oauth2-redirect', include_in_schema=False)
    def oauth_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    @app.get('/docs', include_in_schema=False)
    def documentation():
        response = get_swagger_ui_html(
            openapi_url=app.openapi_url, title='Ouroboros API — Swagger',
            swagger_js_url='/docs/assets/vendor/swagger-ui-bundle.js',
            swagger_css_url='/docs/assets/vendor/swagger-ui.css',
            swagger_ui_parameters={'persistAuthorization':False,'queryConfigEnabled':False},
        )
        html = response.body.decode('utf-8')
        html = html.replace('</head>', '<link rel="stylesheet" href="/docs/assets/authorize.css"></head>')
        html = html.replace('<script>', '<script src="/docs/assets/authorize.js"></script><script>', 1)
        html = html.replace('const ui = SwaggerUIBundle(', 'window.ui = SwaggerUIBundle(')
        html = html.replace('presets: [', 'plugins: [OuroborosAuthPlugin],\npresets: [')
        return HTMLResponse(html, headers={'Cache-Control':'no-store'})

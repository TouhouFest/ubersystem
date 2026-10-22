import cherrypy
from cherrypy.lib.static import serve_file

from uber.config import c
from uber.decorators import all_renderable


@all_renderable()
class Root:
    def index(self, session, id):
        upload = session.upload(id)
        cherrypy.response.headers['Cache-Control'] = 'no-store'
        return serve_file(
            f'{c.UPLOADED_FILES_DIR}/{id[:2]}/{id}',
            content_type=upload.mime
        )

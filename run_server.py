import os

import cherrypy

is_wsgi = __name__ != "__main__" or os.environ.get("GRANIAN") == "true"

if is_wsgi:
    cherrypy.config.update({"environment": "embedded", "engine.signals.on": False})
    cherrypy.server.unsubscribe()

# Initialize CherryPy WSGI settings before importing uber.server
import uber.server  # noqa: F401

if is_wsgi:
    cherrypy.server.unsubscribe()
    cherrypy.engine.start()

application = cherrypy.tree

if __name__ == "__main__":
    cherrypy.engine.start()
    cherrypy.engine.block()

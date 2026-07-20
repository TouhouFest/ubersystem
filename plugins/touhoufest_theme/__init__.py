import os
from uber.utils import static_overrides

def on_load():
    plugin_dir = os.path.dirname(__file__)
    static_dir = os.path.join(plugin_dir, 'static')
    if os.path.isdir(static_dir):
        static_overrides(static_dir)

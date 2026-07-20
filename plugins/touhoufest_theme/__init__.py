import os
from uber.jinja import JinjaEnv
from uber.utils import static_overrides

def on_load():
    plugin_dir = os.path.dirname(__file__)
    static_dir = os.path.join(plugin_dir, 'static')
    if os.path.isdir(static_dir):
        static_overrides(static_dir)

    template_dir = os.path.join(plugin_dir, 'templates')
    if os.path.isdir(template_dir):
        JinjaEnv.insert_template_dir(template_dir)


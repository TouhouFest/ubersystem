import os

from uber.jinja import template_overrides
from uber.server import Root
from uber.utils import static_overrides

from touhoufest_theme.con_info import con_info


def on_load() -> None:
    plugin_dir = os.path.dirname(__file__)
    static_dir = os.path.join(plugin_dir, "static")
    if os.path.isdir(static_dir):
        static_overrides(static_dir)

    template_dir = os.path.join(plugin_dir, "templates")
    if os.path.isdir(template_dir):
        template_overrides(template_dir)

    Root.con_info = con_info

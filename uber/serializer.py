import json
import datetime

class serializer(json.JSONEncoder):
    """
    JSONEncoder subclass for plugins to register serializers for types.
    Plugins should not need to instantiate this class directly, but
    they are expected to call serializer.register() for new data types.
    """

    _registry = {}
    _datetime_format = '%Y-%m-%d %H:%M:%S.%f'

    def default(self, o):
        if type(o) in self._registry:
            preprocessor = self._registry[type(o)]
        else:
            for klass, preprocessor in self._registry.items():
                if isinstance(o, klass):
                    break
            else:
                raise json.JSONEncoder.default(self, o)

        return preprocessor(o)

    @classmethod
    def register(cls, type, preprocessor):
        """
        Associates a type with a preprocessor so that RPC handlers may
        pass non-builtin JSON types.  For example, Ubersystem already
        does the equivalent of

        >>> serializer.register(datetime, lambda dt: dt.strftime('%Y-%m-%d %H:%M:%S.%f'))

        This method raises an exception if you try to register a
        preprocessor for a type which already has one.

        :param type: the type you are registering
        :param preprocessor: function which takes one argument which is
                             the value to serialize and returns a json-
                             serializable value
        """
        assert type not in cls._registry, '{} already has a preprocessor defined'.format(type)
        cls._registry[type] = preprocessor

serializer.register(datetime.date, lambda d: d.strftime('%Y-%m-%d'))
serializer.register(datetime.datetime, lambda dt: dt.strftime(serializer._datetime_format))
serializer.register(set, lambda s: sorted(list(s)))


try:
    import orjson

    def _orjson_default(obj):
        if type(obj) in serializer._registry:
            return serializer._registry[type(obj)](obj)
        for klass, preprocessor in serializer._registry.items():
            if isinstance(obj, klass):
                return preprocessor(obj)
        raise TypeError(f"Type {type(obj)} is not JSON serializable")

    def json_dumps(obj, cls=None):
        if cls is None or cls is serializer:
            return orjson.dumps(obj, default=_orjson_default).decode('utf-8')
        return json.dumps(obj, cls=cls)

    def json_dumps_bytes(obj, cls=None):
        if cls is None or cls is serializer:
            return orjson.dumps(obj, default=_orjson_default)
        return json.dumps(obj, cls=cls).encode('utf-8')

    def json_loads(s):
        return orjson.loads(s)

except ImportError:
    def json_dumps(obj, cls=serializer):
        return json.dumps(obj, cls=cls)

    def json_dumps_bytes(obj, cls=serializer):
        return json.dumps(obj, cls=cls).encode('utf-8')

    def json_loads(s):
        return json.loads(s)


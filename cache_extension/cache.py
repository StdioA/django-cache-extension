from functools import partial

from cache_extension import cache_keys

class ExtensionCache(object):
    """
    Proxy access to the original Cache object's attributes.
    Add more convenient model related ``caches`` API.
    """
    def __init__(self, cache):
        self._cache = cache
        
    def __getattr__(self, name):
        return getattr(self._cache, name)
                                                
    def get_attrs(self, model):
        return dict([(f.attname, getattr(model, f.attname)) for f in model._meta.fields])

    def get_model(self, cls, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise ValueError('multi field should pass by kwargs')
            kwargs = {'pk':args[0]}
        key = cache_keys.key_of_model(cls, **kwargs)
        attrs = self.get(key)
        if attrs:
            fields = set([field.attname for field in cls._meta.fields])
            attrs_keys = set(attrs.keys())
            diff = attrs_keys - fields
            for key in diff:
                attrs.pop(key)
            model = cls(**attrs)
        else:
            model = cls.objects.get(**kwargs)
            self.set(key, self.get_attrs(model))
        return model

    def set_model(self, instance, *args):
        if instance is None:
            raise ValueError("can not cache a none model")
        key = self._make_model_key(instance, *args)
        attrs = self.get_attrs(instance)
        self.set(key, attrs)

    def clear_model(self, instance, *args):
        key = self._make_model_key(instance, *args)
        self.delete(key)

    def clear_models(self, instance, field, vals):
        keys = [cache_keys.key_of_model(instance, **{field:val}) for val in vals]
        self.delete_many(keys)
    
    def get_many_by_vals(self, vals, key_func, version=None):
        keys = [key_func(val) for val in vals]
        ret = self.get_many(keys, version=version)
        if ret:
            _ = {}
            m = dict(zip(keys, vals))
            for k, v in ret.items():
                _[m[k]] = v
            ret = _
        return ret

    def get_models(self, cls, vals, field='pk', version=None, sort=False):
        ''' get multiple models in multiple keys
        '''
        key_func = partial(cache_keys.key_of_model, cls, field)
        models = self.get_many_by_vals(vals, key_func=key_func)
        fields = set([f.attname for f in cls._meta.fields])
        for model in models.values():
            attrs_keys = set(model.keys())
            diff = attrs_keys - fields
            for key in diff:
                model.pop(key)
                
        exists_models = [cls(**m) for m in models.values()]
        if len(exists_models) == len(vals):
            models = exists_models
        else:
            miss_vals = set(vals) - set(models.keys())
            kwargs = {'%s__in' % field: miss_vals}
            miss_models = list(cls.objects.filter(**kwargs))
            data = dict(((key_func(getattr(m, field)), self.get_attrs(m)) for m in miss_models))
            self.set_many(data)
            models = exists_models + miss_models
        if sort:
            models = sorted(models, key=lambda m:vals.index(getattr(m, field)))
        return models

    def get_model_list(self, cls, **kwargs):
        ''' get multiple models in one key
        '''
        key = cache_keys.key_of_model_list(cls, **kwargs)
        models = self.get(key)
        if models:
            return [cls(**model) for model in models]
        models = list(cls.objects.filter(**kwargs))
        data = [self.get_attrs(m) for m in models]
        self.set(key, data)
        return models

    def set_model_list(self, cls, models=None, **kwargs):
        key = cache_keys.key_of_model_list(cls, **kwargs)
        if models is None:
            models = list(cls.objects.filter(**kwargs))
        data = [self.get_attrs(m) for m in models]
        self.set(key, data)

    def clear_model_list(self, instance, *args):
        key = self._make_model_list_key(instance, *args)
        self.delete(key)

    def _make_model_key(self, instance, *args):
        args = args or ['pk']
        kwargs = dict([(field, getattr(instance, field)) for field in args])
        return cache_keys.key_of_model(instance.__class__, **kwargs)
        
    def _make_model_list_key(self, instance, *args):
        kwargs = dict([(field, getattr(instance, field)) for field in args])
        key = cache_keys.key_of_model_list(instance.__class__, **kwargs)
        return key

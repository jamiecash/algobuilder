"""
A collection of utilities for Django.
TODO Create separate projects for collections of similar utils. Open source (MIT) and uploaded to PyPi. Consider
    whether this can be added to django-extensions
"""
import functools
import logging
import pandas as pd

from django.core.cache import caches, InvalidCacheBackendError


# TARGET PROJECT THEME: Caching
# TODO Before this is open sourced, we need to enable support for static methods.
class _Cache(object):
    """
    Decorator to retrieve dataframe output of decorated function from Django cache if it exists. If it doesn't it will
    retrieve from decorated function and store in cache.

    This is only suitable for decorating functions that return a pandas dataframe. It does not work with static methods.

    Dependency: Django must be set up with caching
    """

    # Logger
    __log = logging.getLogger(__name__)

    # Cache name.
    __cache_name = None

    # Wrapped function
    __func = None

    def __init__(self, func, cache_name='default'):
        """
        Decorator to cache the output of a function.
        :param func: The function being decorated
        :param cache_name: The name of the Django cache. Default will use the default cache.

        To configure Django caching see https://docs.djangoproject.com/en/3.2/topics/cache/
        """
        functools.update_wrapper(self, func)
        self.__func = func
        self.__cache_name = cache_name

    def __call__(self, *args, **kwargs):
        """
        Check if it exists in the cache, if not, run the func and store output in cache, else retrieve from cache
        :param args:
        :param kwargs:
        :return: return the decorated function.
        """
        # Session key is func name and passed parameters with spaces and control characters removed and reduced to
        # 200 characters max
        cache_key = f"{self.__func.__name__}_{','.join([f'{x}' for x in args])}_" \
                    f"{','.join([f'{x}={kwargs[x]}' for x in kwargs.keys()])}"
        for char in [" ", "\n"]:
            cache_key = cache_key.replace(char, "")
        cache_key = cache_key[0:200] if len(cache_key) > 200 else cache_key

        # Try and get from cache. If it doesnt exist in cache, then return from wrapped function.
        try:
            cache = caches[self.__cache_name]

            # Get from cache if it exists
            json_txt = cache.get(cache_key, None)

            if json_txt is not None:
                self.__log.debug(f"Retrieved {cache_key} from cache.")
                ret = pd.read_json(json_txt, orient='table')
            else:
                self.__log.debug(f"Retrieving {cache_key} from function.")
                ret = self.__func(self, *args, **kwargs)

                # Save it in cache as JSON
                cache.set(cache_key, ret.to_json(orient='table'))
        except InvalidCacheBackendError as ex:
            # If cache doesnt exist, or there was an error , we will retrieve from the wrapped function.
            self.__log.debug(f"Retrieving {cache_key} from function. Error accessing cache", ex)
            ret = self.__func(self, *args, **kwargs)

        return ret


# wrap _Cache to allow for deferred calling
def django_cache(func=None, cache_name=None):
    if func:
        return _Cache(func)
    else:
        def wrapper(function):
            return _Cache(function, cache_name=cache_name)

        return wrapper

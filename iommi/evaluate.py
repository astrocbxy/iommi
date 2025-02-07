import inspect

from iommi.base import (
    items,
    keys,
)
from iommi.declarative.namespace import (
    func_from_namespace,
    Namespace,
)

_matches_cache = {}


def matches(caller_parameters, callee_parameters, __match_empty=False):
    cache_key = ';'.join((caller_parameters, callee_parameters, str(int(__match_empty))))  # pragma: no mutate
    # (mutation changes this to cached_value = None, which just slows down the code)
    cached_value = _matches_cache.get(cache_key, None)  # pragma: no mutate
    if cached_value is not None:
        return cached_value

    caller = set(caller_parameters.split(',')) if caller_parameters else set()

    a, b, c = callee_parameters.split('|')
    required = set(a.split(',')) if a else set()
    optional = set(b.split(',')) if b else set()
    wildcard = c == '*'

    if not __match_empty and not required and not optional and wildcard:
        result = False  # Special case to not match no-specification function "lambda **whatever: ..."
    else:
        if wildcard:
            result = caller >= required
        else:
            result = required <= caller <= required.union(optional)

    _matches_cache[
        cache_key
    ] = result  # pragma: no mutate (mutation changes result to None which just makes things slower)
    return result


def get_callable_description(c):
    if getattr(c, '__name__', None) == '<lambda>':
        import inspect

        try:
            return 'lambda found at: `{}`'.format(inspect.getsource(c).strip())
        except OSError:  # pragma: no cover
            pass
    return f'`{c}`'


def is_callable(v):
    if isinstance(v, Namespace) and 'call_target' not in v:
        return False
    else:
        return callable(v)


def evaluate(func_or_value, *, __signature=None, __strict=False, __match_empty=True, **kwargs):
    if is_callable(func_or_value):
        if __signature is None:
            __signature = signature_from_kwargs(kwargs)

        callee_parameters = get_signature(func_or_value)
        if callee_parameters is not None and matches(__signature, callee_parameters, __match_empty):
            return func_or_value(**kwargs)

        if __strict:
            assert isinstance(func_or_value, Namespace) and 'call_target' not in func_or_value, (
                "Evaluating {} didn't resolve it into a value but strict mode was active, "
                "the signature doesn't match the given parameters. "
                "We had these arguments: {}".format(
                    get_callable_description(func_or_value),
                    ', '.join(keys(kwargs)),
                )
            )
    return func_or_value


def evaluate_strict(func_or_value, *, __signature=None, __match_empty=True, **kwargs):
    # noinspection PyArgumentEqualDefault
    return evaluate(func_or_value, __signature=None, __strict=True, __match_empty=__match_empty, **kwargs)


def get_signature(func):
    """
    :type func: Callable
    :rtype: str
    """
    try:
        return object.__getattribute__(func, '__iommi_declarative_signature')
    except AttributeError:
        pass

    if isinstance(func, Namespace):
        func = func_from_namespace(func)

    try:
        names, _, varkw, defaults, _, _, _ = inspect.getfullargspec(func)
    except TypeError:
        return None

    first_arg_index = 1 if inspect.ismethod(func) else 0  # Skip self argument on methods

    number_of_defaults = len(defaults) if defaults else 0
    if number_of_defaults > 0:
        required = ','.join(sorted(names[first_arg_index:-number_of_defaults]))
        optional = ','.join(sorted(names[-number_of_defaults:]))
    else:
        required = ','.join(sorted(names[first_arg_index:]))
        optional = ''
    wildcard = '*' if varkw is not None else ''

    signature = '|'.join((required, optional, wildcard))
    try:
        object.__setattr__(func, '__iommi_declarative_signature', signature)
    except TypeError:
        # For classes
        type.__setattr__(func, '__iommi_declarative_signature', signature)
    except AttributeError:
        pass
    return signature


def signature_from_kwargs(kwargs):
    return ','.join(sorted(keys(kwargs)))


def evaluate_members(obj, **kwargs):
    for key in obj._refinables_dynamic:
        evaluate_member(obj, key, **kwargs)


def evaluate_member(obj, key, strict=True, **kwargs):
    value = getattr(obj, key)
    new_value = evaluate(value, __strict=strict, __signature=signature_from_kwargs(kwargs), **kwargs)
    if new_value is not value:
        setattr(obj, key, new_value)


def find_static_items(d):
    if d and isinstance(d, Namespace):
        object.__setattr__(d, '_static_items', {k for k, v in items(d) if not callable(v)})


def evaluate_as_needed(d, kwargs, ignore=()):
    static_items = getattr(d, '_static_items', [])
    return {k: d[k] if k in static_items else evaluate_strict(v, **kwargs) for k, v in items(d) if k not in ignore}


def has_catch_all_kwargs(callback):
    return get_signature(callback).endswith('|*')

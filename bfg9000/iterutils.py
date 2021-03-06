from collections import Iterable
from six import iteritems, string_types
from six.moves import range, zip

__all__ = ['default_sentinel', 'first', 'isiterable', 'iterate', 'listify',
           'merge_dicts', 'merge_into_dict', 'reverse_enumerate', 'tween',
           'uniques', 'unlistify']

# XXX: This could go in a funcutils module if we ever create one...
default_sentinel = object()


def isiterable(thing):
    return isinstance(thing, Iterable) and not isinstance(thing, string_types)


def iterate(thing):
    def generate_none():
        return
        yield

    def generate_one(x):
        yield x

    if thing is None:
        return generate_none()
    elif isiterable(thing):
        return iter(thing)
    else:
        return generate_one(thing)


def listify(thing, always_copy=False, scalar_ok=True):
    if not always_copy and type(thing) == list:
        return thing
    if scalar_ok:
        thing = iterate(thing)
    return list(thing)


def first(thing, default=default_sentinel):
    try:
        return next(iterate(thing))
    except StopIteration:
        if default is not default_sentinel:
            return default
        raise LookupError()


def unlistify(thing):
    if len(thing) == 0:
        return None
    elif len(thing) == 1:
        return thing[0]
    else:
        return thing


def reverse_enumerate(iterable):
    return zip(reversed(range(len(iterable))), reversed(iterable))


def tween(iterable, delim, prefix=None, suffix=None):
    first = True
    for i in iterable:
        if first:
            first = False
            if prefix is not None:
                yield prefix
        else:
            yield delim
        yield i
    if not first and suffix is not None:
        yield suffix


def uniques(iterable):
    def generate_uniques(iterable):
        seen = set()
        for item in iterable:
            if item not in seen:
                seen.add(item)
                yield item
    return list(generate_uniques(iterable))


def merge_into_dict(dst, *args):
    for d in args:
        for k, v in iteritems(d):
            curr = dst.get(k)
            if isinstance(v, dict):
                if curr is None:
                    dst[k] = dict(v)
                elif isinstance(curr, dict):
                    merge_into_dict(curr, v)
                else:
                    raise TypeError('type mismatch for {}'.format(k))
            elif isiterable(v):
                if curr is None:
                    dst[k] = list(v)
                elif isiterable(curr):
                    curr.extend(v)
                elif not isiterable(curr):
                    raise TypeError('type mismatch for {}'.format(k))
            elif v is not None:
                if curr is not None and isiterable(curr):
                    raise TypeError('type mismatch for {}'.format(k))
                dst[k] = v


def merge_dicts(*args):
    dst = {}
    merge_into_dict(dst, *args)
    return dst

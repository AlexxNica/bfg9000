import re
from shlex import shlex
from six import iteritems, string_types

from .. import iterutils
from ..safe_str import jbos, safe_str, shell_literal

__all__ = ['split', 'join', 'listify', 'escape', 'quote_escaped', 'quote',
           'quote_info', 'join_commands', 'local_env', 'global_env']

_bad_chars = re.compile(r'[^\w@%+:,./-]')


def split(s):
    if not isinstance(s, string_types):
        raise TypeError('expected a string')
    lexer = shlex(s, posix=True)
    lexer.commenters = ''
    lexer.escape = ''
    lexer.whitespace_split = True
    return list(lexer)


def join(args):
    return ' '.join(quote(i) for i in args)


def listify(thing):
    if isinstance(thing, string_types):
        return split(thing)
    return iterutils.listify(thing)


def escape(s):
    if not s:
        return '', False
    if not _bad_chars.search(s):
        return s, False
    return s.replace("'", "'\"'\"'"), True


def quote_escaped(s, escaped=True):
    return "'" + s + "'" if escaped else s


def quote(s):
    return quote_escaped(*escape(s))


def quote_info(s):
    s, esc = escape(s)
    return quote_escaped(s, esc), esc


def join_commands(commands):
    return iterutils.tween(commands, shell_literal(' && '))


def local_env(env):
    eq = shell_literal('=')
    return [ jbos(safe_str(name), eq, safe_str(value))
             for name, value in iteritems(env) ]


def global_env(env):
    eq = shell_literal('=')
    return [ ['export', jbos(safe_str(name), eq, safe_str(value))]
             for name, value in iteritems(env) ]

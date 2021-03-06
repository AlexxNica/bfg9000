import re
from collections import namedtuple, OrderedDict
from enum import Enum
from itertools import chain
from six import iteritems, string_types
from six.moves import cStringIO as StringIO

from ... import path
from ... import safe_str
from ... import shell
from ... import iterutils
from ...objutils import objectify
from ...platforms import platform_name, platform_info
from ...tools.common import Command
from ...versioning import Version

__all__ = ['NinjaFile', 'Section', 'Syntax', 'Writer', 'Variable', 'var',
           'Commands', 'path_vars']

Rule = namedtuple('Rule', ['command', 'depfile', 'deps', 'generator', 'pool',
                           'restat'])
Build = namedtuple('Build', ['outputs', 'rule', 'inputs', 'implicit',
                             'order_only', 'variables'])

Syntax = Enum('Syntax', ['output', 'input', 'shell', 'clean'])
Section = Enum('Section', ['path', 'command', 'flags', 'other'])

_comment_tmpl = """
# Do not edit this file! It was automatically generated by bfg9000.
# Instead, you should edit the source file that created this:
# {}
""".strip()


class Writer(object):
    def __init__(self, stream):
        self.stream = stream

    @staticmethod
    def escape_str(string, syntax):
        if '\n' in string:
            raise ValueError('illegal newline')

        if syntax == Syntax.output:
            return re.sub(r'([:$ ])', r'$\1', string)
        elif syntax == Syntax.input:
            return re.sub(r'([$ ])', r'$\1', string)
        elif syntax in [Syntax.shell, Syntax.clean]:
            return string.replace('$', '$$')
        else:
            raise ValueError("unknown syntax '{}'".format(syntax))

    def write_literal(self, string):
        self.stream.write(string)

    def write(self, thing, syntax, shell_quote=shell.quote_info):
        thing = safe_str.safe_str(thing)
        shelly = syntax == Syntax.shell
        escaped = False

        if isinstance(thing, safe_str.literal):
            escaped = True
            self.write_literal(thing.string)
        elif isinstance(thing, safe_str.shell_literal):
            escaped = True
            self.write_literal(self.escape_str(thing.string, syntax))
        elif isinstance(thing, string_types):
            if shelly and shell_quote:
                thing, escaped = shell_quote(thing)
            self.write_literal(self.escape_str(thing, syntax))
        elif isinstance(thing, safe_str.jbos):
            for i in thing.bits:
                escaped |= self.write(i, syntax, shell_quote)
        elif isinstance(thing, path.Path):
            out = Writer(StringIO())
            thing = thing.realize(path_vars, shelly)
            escaped = out.write(thing, syntax, shell.escape)

            thing = out.stream.getvalue()
            if shelly and escaped:
                thing = shell.quote_escaped(thing)
            self.write_literal(thing)
        else:
            raise TypeError(type(thing))

        return escaped

    def write_each(self, things, syntax, delim=safe_str.literal(' '),
                   prefix=None, suffix=None):
        for i in iterutils.tween(things, delim, prefix, suffix):
            self.write(i, syntax)

    def write_shell(self, thing, syntax=Syntax.shell):
        if iterutils.isiterable(thing):
            self.write_each(thing, syntax)
        else:
            self.write(thing, syntax, shell_quote=None)


class Variable(object):
    def __init__(self, name):
        self.name = re.sub('\W', '_', name)

    def use(self):
        return safe_str.literal('${{{}}}'.format(self.name))

    def _safe_str(self):
        return self.use()

    def __str__(self):
        raise NotImplementedError()

    def __repr__(self):
        return repr(self.use())

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, rhs):
        return self.name == rhs.name

    def __add__(self, rhs):
        return self.use() + safe_str.safe_str(rhs)

    def __radd__(self, lhs):
        return safe_str.safe_str(lhs) + self.use()


def var(v):
    return v if isinstance(v, Variable) else Variable(v)


class Commands(object):
    def __init__(self, commands, environ=None):
        if not commands:
            raise ValueError('expected at least one command')
        self.commands = iterutils.listify(commands, scalar_ok=False)
        self.environ = environ or {}

    def use(self):
        out = Writer(StringIO())
        if self.needs_shell and platform_name() == 'windows':
            out.write_literal('cmd /s /c "')

        env_vars = shell.global_env(self.environ)
        for line in shell.join_commands(chain(env_vars, self.commands)):
            out.write_shell(line)

        if self.needs_shell and platform_name() == 'windows':
            out.write_literal('"')
        return safe_str.literal(out.stream.getvalue())

    def _safe_str(self):
        return self.use()

    def convert_args(self, conv):
        def convert(args):
            if iterutils.isiterable(args):
                return Command.convert_args(args, conv)
            return args

        self.commands = [convert(i) for i in self.commands]

    @property
    def needs_shell(self):
        if not self.commands:
            raise ValueError('expected at least one command')
        return (
            len(self.environ) > 0 or
            len(self.commands) > 1 or
            isinstance(self.commands[0], shell.shell_list) or
            not iterutils.isiterable(self.commands[0])
        )


path_vars = {
    path.Root.srcdir:   Variable('srcdir'),
    path.Root.builddir: None,
}
path_vars.update({i: Variable(i.name) for i in path.InstallRoot})

# Only use destdir on platforms that actually support it (e.g. not Windows).
if platform_info().destdir:
    path_vars[path.DestDir.destdir] = Variable('DESTDIR')


class NinjaFile(object):
    Section = Section

    def __init__(self, bfgfile):
        self._bfgfile = bfgfile

        self._min_version = None
        self._var_table = set()
        self._variables = {i: [] for i in Section}

        self._rules = OrderedDict()

        self._builds = []
        self._build_outputs = set()
        self._defaults = []

    def min_version(self, version):
        version = Version(version)
        if self._min_version is None or version > self._min_version:
            self._min_version = version

    def variable(self, name, value, section=Section.other, exist_ok=True):
        name = var(name)
        if self.has_variable(name):
            if not exist_ok:
                raise ValueError("variable {!r} already exists".format(name))
        else:
            self._var_table.add(name)
            self._variables[section].append((name, value))
        return name

    def cmd_var(self, cmd):
        return self.variable(cmd.command_var, cmd.command, Section.command,
                             exist_ok=True)

    def has_variable(self, name):
        return var(name) in self._var_table

    def rule(self, name, command, depfile=None, deps=None, generator=False,
             pool=None, restat=False):
        command = objectify(command, Commands, in_type=object)
        command.convert_args(self.cmd_var)
        if not command.needs_shell:
            command = command.commands[0]

        if pool is not None:
            if pool == 'console':
                self.min_version('1.5')
            else:
                raise ValueError("unknown pool '{}'".format(pool))

        if re.search('\W', name):
            raise ValueError('rule name contains invalid characters')

        if self.has_rule(name):
            raise ValueError("rule '{}' already exists".format(name))

        self._rules[name] = Rule(command, depfile, deps, generator, pool,
                                 restat)

    def has_rule(self, name):
        return name in self._rules

    def build(self, output, rule, inputs=None, implicit=None, order_only=None,
              variables=None):
        if rule != 'phony' and not self.has_rule(rule):
            raise ValueError("unknown rule '{}'".format(rule))

        variables = {var(k): v for k, v in iteritems(variables or {})}

        outputs = iterutils.listify(output)
        for i in outputs:
            if self.has_build(i):
                raise ValueError("build for '{}' already exists".format(i))
            self._build_outputs.add(i)
        self._builds.append(Build(
            outputs, rule, iterutils.listify(inputs),
            iterutils.listify(implicit), iterutils.listify(order_only),
            variables
        ))

    def has_build(self, name):
        return name in self._build_outputs

    def default(self, paths):
        self._defaults.extend(paths)

    def _write_variable(self, out, name, value, syntax=Syntax.shell, indent=0):
        out.write_literal(('  ' * indent) + name.name + ' = ')
        out.write_shell(value, syntax)
        out.write_literal('\n')

    def _write_rule(self, out, name, rule):
        out.write_literal('rule ' + name + '\n')

        self._write_variable(out, var('command'), rule.command, indent=1)
        if rule.depfile:
            self._write_variable(out, var('depfile'), rule.depfile, indent=1)
        if rule.deps:
            self._write_variable(out, var('deps'), rule.deps, indent=1)
        if rule.generator:
            self._write_variable(out, var('generator'), '1', indent=1)
        if rule.pool:
            self._write_variable(out, var('pool'), rule.pool, indent=1)
        if rule.restat:
            self._write_variable(out, var('restat'), '1', indent=1)

    def _write_build(self, out, build):
        out.write_literal('build ')
        out.write_each(build.outputs, Syntax.output)
        out.write_literal(': ' + build.rule)

        lit = safe_str.literal
        out.write_each(build.inputs, Syntax.input, prefix=lit(' '))
        out.write_each(build.implicit, Syntax.input, prefix=lit(' | '))
        out.write_each(build.order_only, Syntax.input, prefix=lit(' || '))
        out.write_literal('\n')

        if build.variables:
            for k, v in iteritems(build.variables):
                self._write_variable(out, k, v, indent=1)

    def write(self, out):
        out = Writer(out)
        out.write_literal(_comment_tmpl.format(self._bfgfile) + '\n\n')

        if self._min_version:
            self._write_variable(
                out, var('ninja_required_version'), str(self._min_version)
            )
            out.write_literal('\n')

        for section in Section:
            # The built-in paths don't need shell quoting because they're used
            # by other paths, which *are* quoted.
            syntax = Syntax.clean if section == Section.path else Syntax.shell
            for name, value in self._variables[section]:
                self._write_variable(out, name, value, syntax)
            if self._variables[section]:
                out.write_literal('\n')

        for name, rule in iteritems(self._rules):
            self._write_rule(out, name, rule)
            out.write_literal('\n')

        for build in self._builds:
            self._write_build(out, build)
            out.write_literal('\n')

        if self._defaults:
            out.write_literal('default ')
            out.write_each(self._defaults, Syntax.input)
            out.write_literal('\n')

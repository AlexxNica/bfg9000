import warnings
from itertools import chain
from six import itervalues
from six.moves import filter as ifilter

from . import builtin
from .. import path
from ..backends.make import writer as make
from ..backends.ninja import writer as ninja
from ..build_inputs import build_input
from ..file_types import Directory, File
from ..iterutils import iterate


@build_input('install')
class InstallOutputs(object):
    def __init__(self, build_inputs, env):
        self._outputs = []

    def add(self, item):
        for i in item.all:
            if i not in self._outputs:
                if not isinstance(i, File):
                    raise TypeError('expected a file or directory')
                if i.external:
                    raise ValueError('external files are not installable')

                self._outputs.append(i)

            for j in i.install_deps:
                self.add(j)

    def __nonzero__(self):
        return self.__bool__()

    def __bool__(self):
        return bool(self._outputs)

    def __iter__(self):
        return iter(self._outputs)


def _can_install(env):
    return all(i is not None for i in itervalues(env.install_dirs))


@builtin.globals('builtins', 'build_inputs', 'env')
def install(builtins, build, env, *args):
    if len(args) == 0:
        raise ValueError('expected at least one argument')

    can_install = _can_install(env)
    if not can_install:
        warnings.warn('unset installation directories; installation of this ' +
                      'build disabled')

    for i in args:
        if can_install:
            build['install'].add(i)
        builtins['default'](i)


def _doppel_cmd(env, buildfile):
    doppel = env.tool('doppel')

    def wrapper(kind):
        cmd = buildfile.cmd_var(doppel)
        basename = cmd.name

        if kind != 'program':
            kind = 'data'
            cmd = [cmd] + doppel.data_args
        if basename.isupper():
            kind = kind.upper()

        name = '{name}_{kind}'.format(name=basename, kind=kind)
        cmd = buildfile.variable(name, cmd, buildfile.Section.command, True)
        return lambda *args, **kwargs: doppel(*args, cmd=cmd, **kwargs)
    return wrapper


def _rm_cmd(env, buildfile):
    rm = env.tool('rm')
    cmd = buildfile.cmd_var(rm)
    return lambda *args, **kwargs: rm(*args, cmd=cmd, **kwargs)


def _install_commands(install_outputs, doppel):
    def install_line(output):
        cmd = doppel(output.install_kind)
        if isinstance(output, Directory):
            if output.files is not None:
                src = [i.path.relpath(output.path) for i in output.files]
                dst = path.install_path(output.path, output.install_root,
                                        directory=True)
                return cmd('into', src, dst, directory=output.path)

            warnings.warn(
                ('installed directory {!r} has no matching files; did you ' +
                 'forget to set `include`?').format(output.path)
            )

        src = output.path
        dst = path.install_path(src, output.install_root)
        return cmd('onto', src, dst)

    return list(chain(
        (install_line(i) for i in install_outputs),
        ifilter(None, (i.post_install for i in install_outputs))
    ))


def _uninstall_commands(install_outputs, rm):
    def uninstall_line(output):
        if isinstance(output, Directory):
            dst = path.install_path(output.path, output.install_root,
                                    directory=True)
            return [dst.append(i.path.relpath(output.path)) for i in
                    iterate(output.files)]
        return [path.install_path(output.path, output.install_root)]

    return [rm(sum((uninstall_line(i) for i in install_outputs), []))]


@make.post_rule
def make_install_rule(build_inputs, buildfile, env):
    install_outputs = build_inputs['install']
    if not install_outputs:
        return

    for i in path.InstallRoot:
        buildfile.variable(make.path_vars[i], env.install_dirs[i],
                           make.Section.path)
    if path.DestDir.destdir in make.path_vars:
        buildfile.variable(make.path_vars[path.DestDir.destdir],
                           env.variables.get('DESTDIR', ''), make.Section.path)

    install = _install_commands(install_outputs, _doppel_cmd(env, buildfile))
    buildfile.rule(target='install', deps='all', recipe=install, phony=True)

    uninstall = _uninstall_commands(install_outputs, _rm_cmd(env, buildfile))
    buildfile.rule(target='uninstall', recipe=uninstall, phony=True)


@ninja.post_rule
def ninja_install_rule(build_inputs, buildfile, env):
    install_outputs = build_inputs['install']
    if not install_outputs:
        return

    for i in path.InstallRoot:
        buildfile.variable(ninja.path_vars[i], env.install_dirs[i],
                           ninja.Section.path)
    if path.DestDir.destdir in ninja.path_vars:
        buildfile.variable(ninja.path_vars[path.DestDir.destdir],
                           env.variables.get('DESTDIR', ''),
                           ninja.Section.path)

    install = _install_commands(install_outputs, _doppel_cmd(env, buildfile))
    ninja.command_build(buildfile, env, output='install', inputs=['all'],
                        commands=install)

    uninstall = _uninstall_commands(install_outputs, _rm_cmd(env, buildfile))
    ninja.command_build(buildfile, env, output='uninstall', commands=uninstall)

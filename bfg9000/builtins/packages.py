import os.path
import re
import warnings

from . import builtin
from .find import find
from ..exceptions import PackageResolutionError, PackageVersionError
from ..file_types import Executable, Framework, Package, CommonPackage
from ..iterutils import default_sentinel, iterate, listify
from ..objutils import objectify
from ..path import Path, Root, which
from ..versioning import check_version, SpecifierSet, Version


class BoostPackage(CommonPackage):
    def __init__(self, name, format, version, **kwargs):
        name = 'boost({})'.format(','.join(iterate(name)))
        CommonPackage.__init__(self, name, format, **kwargs)
        self.version = version


@builtin.globals('env')
@builtin.type(Package)
def package(env, name, version=None, lang='c', kind='any', headers=None,
            libs=default_sentinel):
    if kind not in ('any', 'shared', 'static'):
        raise ValueError("kind must be one of 'any', 'shared', or 'static'")
    version = objectify(version or '', SpecifierSet)
    return env.builder(lang).packages.resolve(name, version, kind, headers,
                                              libs)


# XXX: Remove this after 0.3 is released.
@builtin.globals('builtins')
def system_package(builtins, name, lang='c', kind='any', header=None):
    warnings.warn('system_package is deprecated; please use package instead',
                  DeprecationWarning)
    return builtins['package'](name, lang=lang, kind=kind, headers=header)


# XXX: Remove this after 0.3 is released.
@builtin.globals('builtins')
def pkgconfig_package(builtins, name, lang='c', version=None):
    warnings.warn('pkgconfig_package is deprecated; please use package ' +
                  'instead', DeprecationWarning)
    return builtins['package'](name, version=version, lang=lang)


@builtin.globals('env')
@builtin.type(Executable)
def system_executable(env, name, format=None):
    # XXX: Come up with a better way to handle `which()` returning a list?
    return Executable(
        Path(which([[name]], env.variables, resolve=True)[0], Root.absolute),
        format or env.platform.object_format, external=True
    )


@builtin.globals('env')
def framework(env, name, suffix=None):
    if not env.platform.has_frameworks:
        raise ValueError("{} platform doesn't support frameworks".format(
            env.platform.name
        ))

    framework = Framework(name, suffix)
    return CommonPackage(framework.full_name, env.platform.object_format,
                         libs=[framework])


def _boost_version(header, required_version=None):
    version_hpp = header.path.append('boost').append('version.hpp')
    with open(version_hpp.string()) as f:
        for line in f:
            m = re.match(r'#\s*define\s+BOOST_LIB_VERSION\s+"([\d_]+)"', line)
            if m:
                version = Version(m.group(1).replace('_', '.'))
                check_version(version, required_version, 'boost',
                              PackageVersionError)
                return version
    raise PackageVersionError('unable to parse "boost/version.hpp"')


@builtin.globals('env')
def boost_package(env, name=None, version=None):
    version = objectify(version or '', SpecifierSet)
    pkg = env.builder('c++').packages
    version_hpp = 'boost/version.hpp'

    root = env.getvar('BOOST_ROOT')
    incdir = env.getvar('BOOST_INCLUDEDIR', os.path.join(root, 'include')
                        if root else None)
    libdir = env.getvar('BOOST_LIBRARYDIR', os.path.join(root, 'lib')
                        if root else None)

    if incdir:
        header = pkg.header(version_hpp, [incdir])
        boost_version = _boost_version(header, version)
    else:
        # On Windows, check the default install location, which is structured
        # differently from other install locations.
        if env.platform.name == 'windows':
            dirs = find(r'C:\Boost\include', 'boost-*', type='d', flat=True)
            if dirs:
                try:
                    header = pkg.header(version_hpp, [max(dirs)])
                    boost_version = _boost_version(header, version)
                    return BoostPackage(
                        name, env.builder('c++').object_format, boost_version,
                        includes=[header], lib_dirs=[r'C:\Boost\lib'],
                    )
                except PackageResolutionError:
                    pass

        header = pkg.header(version_hpp)
        boost_version = _boost_version(header, version)

    if env.platform.name == 'windows':
        if not env.builder('c++').auto_link:
            # XXX: Don't require auto-link.
            raise PackageResolutionError('Boost on Windows requires auto-link')
        return BoostPackage(
            name, env.builder('c++').object_format, boost_version,
            includes=[header], lib_dirs=listify(libdir),
        )
    else:
        extra_kwargs = {}
        if env.platform.flavor == 'posix' and 'thread' in iterate(name):
            extra_kwargs['pthread'] = True
        dirs = [libdir] if libdir else None
        return BoostPackage(
            name, env.builder('c++').object_format, boost_version,
            includes=[header],
            libs=[pkg.library('boost_' + i, search_dirs=dirs)
                  for i in iterate(name)],
            **extra_kwargs
        )

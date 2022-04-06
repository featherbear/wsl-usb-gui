from pkg_resources import get_distribution, DistributionNotFound


def version_scheme():
    from setuptools_scm import version

    def local_scheme(vers):
        return vers.format_choice(clean_format="+{node}", dirty_format="+{node}.dirty")

    def version_scheme(vers):
        version.SEMVER_LEN = 2
        ver = version.guess_next_simple_semver(
            vers.tag, retain=version.SEMVER_LEN, increment=not vers.exact
        )
        return ver

    return {"local_scheme": local_scheme, "version_scheme": version_scheme}


try:
    __version__ = get_distribution("tinycom").version
except DistributionNotFound:
    # package is not installed
    try:
        import setuptools_scm

        __version__ = setuptools_scm.get_version(
            root="..", relative_to=__file__, **version_scheme()
        )
    except ImportError:
        # setuptools_scm not yet installed
        __version__ = None

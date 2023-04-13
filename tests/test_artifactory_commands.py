import os
import tempfile

from tools import run

try:
    # to test locally with an artifactory instance that already has
    # extensions-stg and extensions-prod repos, define this dict of credentials
    # in credentials.py (the file is gitignored)

    # environment = {
    #     "CONAN_LOGIN_USERNAME_EXTENSIONS_PROD": "......",
    #     "CONAN_PASSWORD_EXTENSIONS_PROD": "......",
    #     "CONAN_LOGIN_USERNAME_EXTENSIONS_STG": "......",
    #     "CONAN_PASSWORD_EXTENSIONS_STG": "......",
    #     "ART_URL": "https://url/artifactory",
    # }

    from credentials import environment
except ImportError:
    environment = {}

import pytest


@pytest.fixture(autouse=True)
def conan_test():
    old_env = dict(os.environ)
    env_vars = {"CONAN_HOME": tempfile.mkdtemp(suffix='conans')}
    os.environ.update(env_vars)
    os.environ.update(environment)
    current = tempfile.mkdtemp(suffix="conans")
    cwd = os.getcwd()
    os.chdir(current)
    run("conan profile detect")
    run(f'conan remote add extensions-prod {os.getenv("ART_URL")}/api/conan/extensions-prod')
    run(f'conan remote add extensions-stg {os.getenv("ART_URL")}/api/conan/extensions-stg')

    try:
        yield
    finally:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(old_env)


def test_build_info_create():
    repo = os.path.join(os.path.dirname(__file__), "..")

    build_name = "mybuildinfo"
    build_number = "1"

    run(f"conan config install {repo}")
    run("conan new cmake_lib -d name=mypkg -d version=1.0 --force")

    run("conan create . --format json -tf='' -s build_type=Release > create_release.json")
    run("conan create . --format json -tf='' -s build_type=Debug > create_debug.json")

    run("conan remove mypkg* -c -r extensions-stg")
    run("conan remove mypkg* -c -r extensions-prod")

    run("conan upload mypkg/1.0 -c -r extensions-stg")

    run(f'conan art:build-info create create_release.json {build_name}_release {build_number} > {build_name}_release.json')
    run(f'conan art:build-info create create_debug.json {build_name}_debug {build_number} > {build_name}_debug.json')

    run(f'conan art:property build-info-add {build_name}_release.json {os.getenv("ART_URL")} extensions-stg --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')
    run(f'conan art:property build-info-add {build_name}_debug.json {os.getenv("ART_URL")} extensions-stg --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')

    run(f'conan art:build-info upload {build_name}_release.json {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')
    run(f'conan art:build-info upload {build_name}_debug.json {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')

    # aggregate the release and debug build infos into an aggregated one
    # we also have to set the properties so that the paths to the artifacts are linked
    # with the build info in Artifactory
    run(f'conan art:build-info append {build_name}_aggregated {build_number} --build-info={build_name}_release.json --build-info={build_name}_debug.json > {build_name}_aggregated.json')
    run(f'conan art:build-info upload {build_name}_aggregated.json {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')
    run(f'conan art:property build-info-add {build_name}_aggregated.json {os.getenv("ART_URL")} extensions-stg --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')

    run(f'conan art:build-info get {build_name}_release {build_number} {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')
    run(f'conan art:build-info get {build_name}_debug {build_number} {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')
    run(f'conan art:build-info get {build_name}_aggregated {build_number} {os.getenv("ART_URL")} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')

    run(f'conan art:build-info promote {build_name}_aggregated {build_number} {os.getenv("ART_URL")} extensions-stg extensions-prod --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}"')

    # The local clean is because later I'm going to do a conan install from prod repo 
    # and I want to make sure that the install succeeds because the package comes from 
    # the remote and not because it's already in the cache. 
    run('conan remove mypkg* -c')

    # we have to remove the package from the source repo because in the Conan promotion we copy
    # Conan promotions must always be copy, and the clean must be handled manually
    # otherwise you can end up deleting recipe artifacts that other packages use
    run('conan remove mypkg* -c -r extensions-stg')

    # check that we can install from the prod repo after the promotion
    run('conan install --requires=mypkg/1.0 -r extensions-prod -s build_type=Release')
    run('conan install --requires=mypkg/1.0 -r extensions-prod -s build_type=Debug')

    run(f'conan art:build-info delete {build_name}_release {os.getenv("ART_URL")} --build-number={build_number} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}" --delete-all --delete-artifacts')
    run(f'conan art:build-info delete {build_name}_debug {os.getenv("ART_URL")} --build-number={build_number} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}" --delete-all --delete-artifacts')
    run(f'conan art:build-info delete {build_name}_aggregated {os.getenv("ART_URL")} --build-number={build_number} --user="{os.getenv("CONAN_LOGIN_USERNAME_EXTENSIONS_STG")}" --password="{os.getenv("CONAN_PASSWORD_EXTENSIONS_STG")}" --delete-all --delete-artifacts')

    # even deleting the builds, the folders will stay there, so manually cleaning
    run('conan remove mypkg* -c -r extensions-prod')


def test_fail_if_not_uploaded():
    """
    In order to create the Build Info we need the hashes of the artifacts that are uploaded
    to Artifactory, but those artifacts: conan_source.tgz, conan_package.tgz, etc.
    are only created on the upload process, that's why we need an upload previous to 
    creating the Build Infos. If those artifacts are not in the cache, we raise.
    """

    repo = os.path.join(os.path.dirname(__file__), "..")

    build_name = "mybuildinfo"
    build_number = "1"

    run(f"conan config install {repo}")

    run("conan new cmake_lib -d name=mypkg -d version=1.0 --force")

    run("conan create . --format json -tf='' > create.json")

    out = run(f'conan art:build-info create create.json {build_name} {build_number}', error=True)

    assert "Artifacts are missing in the cache" in out
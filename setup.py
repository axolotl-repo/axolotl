import setuptools # type: ignore
import sys
import os
from pathlib import Path

REPO_URL = "https://github.com/axolotl-repo/axolotl"

def get_description():
#    from pathlib import Path
    import re
    readme_md = Path("README.md")
    text = readme_md.read_text(encoding="utf-8")

    # rewrite any relative paths to version-specific absolute paths
    sub = r'\1' + REPO_URL + "/blob/v0.1.0" + r'/\2'
    text = re.sub(r'(src=")((?!https?://))', sub, text)
    text = re.sub(r'(\[.*?\]\()((?!https?://))', sub, text)

    return text


def cxx_version(v):
    return [f"-std={v}" if sys.platform != "win32" else f"/std:{v}"]

def platform_compile_args():
    # If flags are specified as a global env var use them,
    # this happens during conda build,
    # and is needed to override build configurations on osx
    flags = os.environ.get("CXXFLAGS", "").split()
    if flags:
        return flags

    # Otherwise default to a multi-arch build
    if sys.platform == 'darwin':
        return "-arch x86_64 -arch arm64 -arch arm64e".split()
    if sys.platform == 'win32':
        return ['/MT']  # avoids creating Visual Studio dependencies
    return []

def platform_link_args():
    if sys.platform != 'win32':
        return platform_compile_args() # clang/gcc is used
    return []

def limited_api_args():
    # We would like to use METH_FASTCALL, but that's only available in the
    # Python 3.10+ stable ABI, and we'd like to support Python 3.8+
    #
    # To re-enable, we also need setup.cfg with
    #
    # [bdist_wheel]
    # py-limited-api=cp310
    #
    #    return ['-DPy_LIMITED_API=0x030a0000']
    return []

setuptools.setup(
    name="axolotl",
    version='0.1.0',
    description="Automated Program Repair at Runtime",
    keywords="repair runtime",
    long_description=get_description(),
    long_description_content_type="text/markdown",
    url=REPO_URL,
    author="",
    author_email="",
    license="Apache License 2.0",
    packages=['axolotl','axolotl.san2patch'],
    package_dir={'': 'src'},
    package_data={'': ['main.native']},
    install_requires=[
        "bytecode",
        "dill",
        "psutil"
    ],
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows :: Windows 10"
    ]
)
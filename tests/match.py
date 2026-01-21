from fnmatch import fnmatch

import os


PATTERNS = [
    "*.exe",
    # "*.pyc",
    "*config-3*",
    "*tcl*",
    "*tdbc*",
    "*tk*",
    "__phello__",
    "__pycache__",
    "_codecs_*.so",
    "_test*",
    "_tk*",
    "_xx*.so",
    "distutils",
    "ensurepip",
    "idlelib",
    "lib2to3",
    "libpython*",
    "LICENSE.txt",
    "pkgconfig",
    "pydoc_data",
    "site-packages",
    "test",
    "Tk*",
    "turtle*",
    "venv",
    "xx*.so",
]

def match(entry) -> bool:
    return any(fnmatch(entry, p) for p in PATTERNS)

def remove(entry, prefix=''):
    print(prefix, entry)
    os.system(f"rm -rf {entry}")

def walk(root='.', match_func=match, action_func=remove):
    for root, dirs, filenames in os.walk(root):
        if ".git" in dirs:
            dirs.remove('.git')
        for d in dirs:
            current = os.path.join(root, d)
            if match_func(d):
                action_func(current, ' +-->')

        for f in filenames:
            current = os.path.join(root, f)
            if match_func(f):
                action_func(current, ' |-->')

walk("build/install/python/lib")

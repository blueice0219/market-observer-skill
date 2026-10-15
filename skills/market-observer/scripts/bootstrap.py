"""Copy the bundled app into a new deployment; optionally install dependencies."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def bootstrap(target, install=False):
    source = Path(__file__).resolve().parents[1] / 'assets' / 'app'
    target = Path(target).resolve()
    if target == source or source in target.parents:
        raise ValueError('Choose a deployment outside the skill assets directory')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('Target is not empty; reuse the existing deployment instead of overwriting it')
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '*.egg-info', '.venv', 'data'))
    if install:
        venv.EnvBuilder(with_pip=True).create(target / '.venv')
        python = target / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        subprocess.run([str(python), '-m', 'pip', 'install', '-e', '.[live]'], cwd=target, check=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    try:
        print(bootstrap(args.target, args.install))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()

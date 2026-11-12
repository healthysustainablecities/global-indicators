"""
Back up and restore a study region database.

Writes a portable PostgreSQL custom-format dump of a processed study region's
database, with a YAML sidecar recording what it holds, and restores such a
dump into a GHSCI PostGIS server, on this computer or another.  A dump is the
only copy of a region's results that survives the PostGIS container being
re-created, so it is worth making one for any region that took long to
analyse.

From the process folder:
    python subprocesses/_database_backup.py dump <codename or config> [path]
    python subprocesses/_database_backup.py restore <dump file> [--overwrite]

Or in Python:
    ghsci.dump('ES_Las_Palmas_2025')     # or r.dump()
    ghsci.restore('data/_database_backups/es_las_palmas_2025_20260926.dump')

pg_dump and pg_restore must be at least the server's major version; the
GHSCI image's conda environment provides them (18.4 in v4.15.0), newer than
the PostGIS server (15).  Dumps they write use an archive format the server
container's own pg_restore cannot read, so restore them through GHSCI.
Where the clients are unavailable, the equivalent commands to run from the
host through the PostGIS container are printed instead.
"""

import datetime
import getpass
import hashlib
import os
import re
import shutil
import subprocess
import sys

SERVER_CONTAINER = 'ghscic_postgis'
DUMP_EXTENSIONS = ('.dump', '.backup')
DEFAULT_FOLDER = '_database_backups'
TOC_TABLE = re.compile(
    r'^\d+; \d+ \d+ TABLE (?!DATA )(\S+) (\S+) ',
    re.MULTILINE,
)


def dump_filename(db: str, date=None) -> str:
    """Return a dated dump filename for a database, e.g. db_20260926.dump."""
    date = date or datetime.date.today()
    return f'{db}_{date:%Y%m%d}.dump'


def resolve_dump_path(path, db: str, default_folder: str, date=None) -> str:
    """Resolve a dump file path from a file or folder path (or None)."""
    if path is None:
        return os.path.join(default_folder, dump_filename(db, date))
    if str(path).lower().endswith(DUMP_EXTENSIONS):
        return str(path)
    return os.path.join(str(path), dump_filename(db, date))


def major_version(text) -> int | None:
    """Return the PostgreSQL major version from a version string or number.

    Accepts 'pg_dump (PostgreSQL) 15.13 (Debian ...)', '15.13' or a
    server_version_num such as 150013.
    """
    if text is None:
        return None
    text = str(text).strip()
    if text.isdigit() and len(text) >= 5:
        return int(text) // 10000
    match = re.search(r'(?:PostgreSQL\)\s*)?(\d+)', text)
    return int(match.group(1)) if match else None


def client_supports(client_major, server_major) -> bool:
    """Whether a pg_dump/pg_restore client can work with a server version."""
    if client_major is None or server_major is None:
        return False
    return int(client_major) >= int(server_major)


def parse_toc_header(text: str) -> dict:
    """Parse the header of a 'pg_restore -l' listing into a dictionary.

    Keys are lower case with underscores, e.g. 'dbname', 'dump_version',
    'dumped_from_database_version'; 'tables' counts the TABLE entries.
    """
    header = {}
    for line in text.splitlines():
        match = re.match(r';\s+([A-Za-z][A-Za-z ]*?):\s+(.*\S)\s*$', line)
        if match:
            key = match.group(1).strip().lower().replace(' ', '_')
            header[key] = match.group(2)
    header['tables'] = len(TOC_TABLE.findall(text))
    return header


def host_dump_commands(
    db: str,
    filename: str,
    container=SERVER_CONTAINER,
    port=5433,
) -> list:
    """Commands to dump a database from the host via the PostGIS container.

    The dump is written inside the container and copied out, since
    redirecting binary output in Windows PowerShell corrupts it.
    """
    return [
        f'docker exec {container} pg_dump -p {port} -U postgres -Fc -Z 6 -f /tmp/{filename} {db}',
        f'docker cp {container}:/tmp/{filename} {filename}',
        f'docker exec {container} rm /tmp/{filename}',
    ]


def host_restore_commands(
    filename: str,
    db: str = None,
    container=SERVER_CONTAINER,
    port=5433,
    jobs=4,
) -> list:
    """Commands to restore a dump from the host via the PostGIS container."""
    name = os.path.basename(filename)
    commands = [
        f'docker cp {filename} {container}:/tmp/{name}',
        f'docker exec {container} pg_restore -p {port} -U postgres --create --no-owner --no-acl -j {jobs} -d postgres /tmp/{name}',
    ]
    if db:
        commands.append(
            f'docker exec {container} psql -p {port} -U postgres -d {db} -c "SELECT count(*) FROM pg_tables WHERE schemaname = \'public\'"',
        )
    commands.append(f'docker exec {container} rm /tmp/{name}')
    return commands


def restore_errors(stderr: str) -> list:
    """Return pg_restore's error messages, less those known to be benign.

    A pg_restore newer than the server sets parameters the server doesn't
    have (transaction_timeout, from PostgreSQL 17) on each connection;
    nothing is lost when these fail.
    """
    benign = ('transaction_timeout',)
    return [
        line.strip()
        for line in stderr.splitlines()
        if re.search('error:', line, re.IGNORECASE)
        and not any(b in line for b in benign)
    ]


def sha256(path: str, block=1 << 20) -> str:
    """Return the SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _print_commands(heading: str, commands: list):
    print(f'\n{heading}\n')
    for command in commands:
        print(f'  {command}')
    print()


def _client_major(program: str):
    """Return the major version of a PostgreSQL client program, if found."""
    executable = shutil.which(program)
    if executable is None:
        return None
    result = subprocess.run(
        [executable, '--version'],
        capture_output=True,
        text=True,
    )
    return major_version(result.stdout)


def _connect(db: str):
    import ghsci
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    sql = ghsci.settings['sql']
    conn = psycopg2.connect(
        dbname=db,
        user=sql['db_user'],
        password=sql['db_pwd'],
        host=sql['db_host'],
        port=sql['db_port'],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def _database_exists(db: str) -> bool:
    import ghsci

    conn = _connect(ghsci.settings['sql']['admin_db'])
    with conn.cursor() as curs:
        curs.execute('SELECT 1 FROM pg_database WHERE datname = %s', (db,))
        exists = curs.fetchone() is not None
    conn.close()
    return exists


def database_summary(db: str) -> dict:
    """Describe a database: server and extension versions, tables, size."""
    conn = _connect(db)
    with conn.cursor() as curs:
        curs.execute('SHOW server_version_num')
        server_version_num = int(curs.fetchone()[0])
        curs.execute('SHOW server_version')
        server_version = curs.fetchone()[0]
        curs.execute(
            'SELECT extname, extversion FROM pg_extension ORDER BY extname',
        )
        extensions = dict(curs.fetchall())
        curs.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'",
        )
        tables = curs.fetchone()[0]
        curs.execute('SELECT pg_database_size(current_database())')
        size = curs.fetchone()[0]
    conn.close()
    return {
        'server_version': server_version,
        'server_version_num': server_version_num,
        'extensions': extensions,
        'tables': tables,
        'database_bytes': size,
    }


def _size(n: int) -> str:
    for unit in ('bytes', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:,.0f} {unit}' if unit == 'bytes' else f'{n:,.1f} {unit}'
        n /= 1024


def _display_path(path: str) -> str:
    """Express a path relative to the process folder, where GHSCI runs."""
    import ghsci

    try:
        relative = os.path.relpath(
            path,
            os.path.join(ghsci.folder_path, 'process'),
        )
    except ValueError:
        return path
    return path if relative.startswith('..') else relative.replace('\\', '/')


def dump_database(r=None, path=None, database=None, compress=6):
    """Dump a study region's database to a portable custom-format file.

    r is a Region (or None when a bare database name is given); path is a
    folder or .dump file, by default process/data/_database_backups.
    Returns the dump path, or None if the dump could not be made here.
    """
    import ghsci
    import yaml

    db = database or r.config['db']
    target = resolve_dump_path(
        path,
        db,
        os.path.join(ghsci.data_path, DEFAULT_FOLDER),
    )
    filename = os.path.basename(target)
    if not _database_exists(db):
        print(
            f'Database "{db}" was not found on the PostGIS server; '
            'has analysis been run for this region?',
        )
        return None
    summary = database_summary(db)
    server = summary['server_version_num'] // 10000
    client = _client_major('pg_dump')
    if not client_supports(client, server):
        reason = (
            'pg_dump is not installed in this container'
            if client is None
            else f'pg_dump {client} is older than the PostgreSQL {server} server'
        )
        print(f'\n{reason}, so the dump cannot be made from here.')
        _print_commands(
            'Run these from a terminal on the host computer instead '
            '(PowerShell, or bash; do not redirect pg_dump output to a file):',
            host_dump_commands(db, filename),
        )
        return None

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    print(
        f'Dumping "{db}" ({_size(summary["database_bytes"])}, '
        f'{summary["tables"]} tables) to {_display_path(target)} ...',
        flush=True,
    )
    start = datetime.datetime.now()
    subprocess.run(
        ['pg_dump', '-Fc', f'-Z{compress}', '-d', db, '-f', target],
        check=True,
    )
    elapsed = (datetime.datetime.now() - start).total_seconds()
    dump_bytes = os.path.getsize(target)
    record = {
        'database': db,
        'codename': r.codename if r is not None else None,
        'configuration': r.config.get('yaml') if r is not None else None,
        'created': datetime.datetime.now().isoformat(timespec='seconds'),
        'ghsci_release': ghsci.__version__,
        'ghsci_environment': ghsci.__environment__,
        'pg_dump_version': client,
        'dump_bytes': dump_bytes,
        'sha256': sha256(target),
        **summary,
    }
    if record['configuration']:
        record['configuration'] = _display_path(record['configuration'])
    with open(f'{target}.yml', 'w', encoding='utf-8') as f:
        yaml.safe_dump(record, f, sort_keys=False, allow_unicode=True)
    print(
        f'Done: {_size(dump_bytes)} in {elapsed:.0f} s '
        f'(checksum and details in {filename}.yml).',
    )
    _print_dump_tips(record, target)
    return target


def _print_dump_tips(record: dict, target: str):
    filename = os.path.basename(target)
    config = record.get('configuration')
    server = record['server_version_num'] // 10000
    print('\nTo restore it, here or on another computer running GHSCI:')
    print(f"  ghsci.restore('{_display_path(target)}')")
    if record.get('pg_dump_version', server) <= server:
        _print_commands(
            'or, from a terminal on the host:',
            host_restore_commands(filename, record['database']),
        )
    else:
        print(
            f'  (It was written by pg_dump {record["pg_dump_version"]}, so '
            f"the database container's own pg_restore {server} cannot read "
            'it; restore it through GHSCI as above.)\n',
        )
    print('Tips:')
    print(
        f'  - Keep {filename}.yml with the dump: restore uses it to check '
        'the result.',
    )
    if config:
        print(
            f'  - Also copy the configuration ({config}) and, to keep reports '
            'and goalposts, the region\'s _study_region_outputs folder.',
        )
    print(
        f'  - Restore to PostgreSQL {record["server_version_num"] // 10000} '
        'or newer, with the same or newer PostGIS/pgRouting.',
    )
    print(
        '  - Keep the dump somewhere safe: databases live in the PostGIS '
        "container's Docker volume, which re-creating the container can "
        'orphan.\n',
    )


def _read_toc(path: str) -> dict:
    result = subprocess.run(
        ['pg_restore', '-l', path],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_toc_header(result.stdout)


def _read_sidecar(path: str) -> dict:
    import yaml

    sidecar = f'{path}.yml'
    if not os.path.exists(sidecar):
        return {}
    with open(sidecar, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def restore_database(path: str, overwrite=False, jobs=4):
    """Restore a database dump made by dump_database (or pg_dump -Fc).

    The database is re-created under its original name, with its settings.
    An existing database of that name is only replaced if overwrite=True,
    after confirmation.  Returns the database name, or None.
    """
    import ghsci

    if not os.path.exists(path):
        print(f'Dump file not found: {path}')
        return None
    sidecar = _read_sidecar(path)
    client = _client_major('pg_restore')
    if client is None:
        print(
            '\npg_restore is not installed in this container, so the dump '
            'cannot be restored from here.',
        )
        _print_commands(
            'From a terminal on the host, in the folder holding the dump:',
            host_restore_commands(
                os.path.basename(path),
                sidecar.get('database'),
            ),
        )
        return None
    header = _read_toc(path)
    db = header.get('dbname')
    if not db:
        print(f'Could not read a database name from {path}.')
        return None
    admin_db = ghsci.settings['sql']['admin_db']
    if _database_exists(db):
        if not overwrite:
            print(
                f'\nDatabase "{db}" already exists, so it was not replaced.  '
                'To replace it, drop it first (r.drop()) or run\n'
                f"  ghsci.restore('{_display_path(path)}', overwrite=True)\n",
            )
            return None
        password = ghsci.settings['sql']['db_pwd']
        answer = getpass.getpass(
            prompt=f'Replace existing database "{db}"?  '
            f"Please enter '{password}' to confirm:",
        )
        if answer != password:
            print('Not confirmed; nothing was changed.')
            return None
        conn = _connect(admin_db)
        with conn.cursor() as curs:
            try:
                curs.execute(f'DROP DATABASE IF EXISTS "{db}";')
            except Exception as e:
                print(
                    f'Could not drop "{db}"; check that it is not open in '
                    f'another program (QGIS, psql, a notebook).\n{e}',
                )
                conn.close()
                return None
        conn.close()

    print(
        f'Restoring "{db}" from {_display_path(path)} '
        f'(dumped from PostgreSQL {header.get("dumped_from_database_version", "?").split()[0]}) ...',
        flush=True,
    )
    start = datetime.datetime.now()
    result = subprocess.run(
        [
            'pg_restore',
            '--create',
            '--no-owner',
            '--no-acl',
            '-j',
            str(jobs),
            '-d',
            admin_db,
            path,
        ],
        capture_output=True,
        text=True,
    )
    elapsed = (datetime.datetime.now() - start).total_seconds()
    if not _database_exists(db):
        print(f'Restore failed:\n{result.stderr.strip()}')
        return None
    errors = restore_errors(result.stderr)
    if errors:
        print(
            f'pg_restore reported {len(errors)} error(s); the first were:\n  '
            + '\n  '.join(errors[:5]),
        )
    conn = _connect(db)
    with conn.cursor() as curs:
        curs.execute(ghsci.grant_query)
    conn.close()
    summary = database_summary(db)
    expected = sidecar.get('tables')
    check = (
        f', matching the {expected} recorded at dump'
        if expected == summary['tables']
        else f'; {expected} were recorded at dump'
        if expected
        else ''
    )
    print(
        f'Done in {elapsed:.0f} s: "{db}" has {summary["tables"]} '
        f'tables{check}.',
    )
    config = sidecar.get('configuration') or '<codename or configuration path>'
    print(
        '\nNext steps:\n'
        f"  r = ghsci.Region('{config}')\n"
        '  r.get_tables()\n'
        'The region configuration must be present on this computer.  Input '
        'data are only needed to re-run analysis; a region already analysed '
        'loads with a warning if they are missing.\n',
    )
    return db


def main():
    import ghsci

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if len(args) < 2 or args[0] not in ('dump', 'restore'):
        print(__doc__)
        return
    if args[0] == 'dump':
        path = args[2] if len(args) > 2 else None
        ghsci.dump(args[1], path=path)
    else:
        ghsci.restore(args[1], overwrite='--overwrite' in flags)


if __name__ == '__main__':
    main()

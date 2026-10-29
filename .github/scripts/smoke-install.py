"""Exercise image-only Compose in disposable volumes, never an operator's .env."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import time
import uuid

PROJECT = 'minifiles'
PREFIX = PROJECT.upper()
ROOT = Path(__file__).resolve().parents[2]
MINIFILES = PROJECT == 'minifiles'
SERVICE = 'minifiles' if MINIFILES else 'app'


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


with tempfile.TemporaryDirectory(prefix=f'{PROJECT}-install-') as directory:
    work = Path(directory)
    shutil.copyfile(ROOT / 'compose.yaml', work / 'compose.yaml')
    # Scrub interpolation overrides, including variables exported by a local operator.
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith(('COMPOSE_', PREFIX + '_', 'APP_', 'DB_', 'SESSION_', 'IGDB_')):
            environment.pop(key)
    values = {
        PREFIX + '_IMAGE': f'{PROJECT}:ci',
        PREFIX + '_USERNAME': 'ci-user',
    }
    if MINIFILES:
        values.update({
            'MINIFILES_PASSWORD': 'only-for-disposable-ci-42',
            'MINIFILES_ORIGIN': 'https://127.0.0.1:8090',
            'MINIFILES_TLS_HOST': '127.0.0.1',
            'MINIFILES_HTTPS_IMAGE': 'minifiles-https:ci',
            'MINIFILES_PORT': '0',
            'MINIFILES_UID': str(os.getuid()),
            'MINIFILES_GID': str(os.getgid()),
        })
        for name in ('local-data', 'local-config', 'tls-data'):
            (work / name).mkdir(mode=0o700)
    else:
        password_hash = run(['docker', 'run', '--rm', '--entrypoint', 'php', f'{PROJECT}:ci',
                             '-r', 'echo password_hash("only-for-disposable-ci-42", PASSWORD_BCRYPT);'])
        values.update({
            'APP_KEY': 'base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
            PREFIX + '_PASSWORD_HASH': password_hash,
            PREFIX + ('_HTTP_PORT' if PROJECT == 'soloinventory' else '_PORT'): '0',
        })
    (work / '.env').write_text(''.join(f"{key}='{value}'\n" for key, value in values.items()))
    (work / '.env').chmod(0o600)
    command = ['docker', 'compose', '--project-directory', str(work), '--env-file', str(work / '.env'),
               '-p', f'{PROJECT}-ci-{uuid.uuid4().hex[:10]}', '-f', str(work / 'compose.yaml')]

    def compose(*args):
        return run(command + list(args), env=environment)

    def execute(*args):
        return compose('exec', '-T', SERVICE, *args)

    def check_web():
        target = 'https' if MINIFILES else 'app'
        internal = '8443' if MINIFILES else ('8080' if PROJECT == 'soloinventory' else '80')
        address = compose('port', target, internal).splitlines()[0]
        scheme, endpoint = ('https', '/health') if MINIFILES else ('http', '/up')
        args = ['curl', '--fail', '--silent', '--show-error', '--connect-timeout', '5',
                '--max-time', '10', '--retry', '15',
                '--retry-delay', '1', '--retry-all-errors']
        if MINIFILES:
            cert = work / 'tls-data/caddy/pki/authorities/local/root.crt'
            for _ in range(30):
                if cert.is_file():
                    break
                time.sleep(1)
            args += ['--cacert', str(cert)]
        run(args + [scheme + '://' + address + endpoint])
        run(args + [scheme + '://' + address + '/'])

    try:
        compose('config', '--quiet')
        compose('up', '-d', '--wait', '--wait-timeout', '180', '--pull', 'never')
        check_web()
        if MINIFILES:
            execute('python', '-c', 'from pathlib import Path; from backend.database import Database; '
                    'Database(Path("/config")).save_section(dict(id="ci",name="Keep",path="Keep",color="blue",position=0)); '
                    'Path("/data/ci-proof.txt").write_text("keep")')
            certificate = (work / 'tls-data/caddy/pki/authorities/local/root.crt').read_bytes()
        else:
            execute('php', '-r', '$db = new PDO("sqlite:".getenv("DB_DATABASE")); '
                    '$db->exec("CREATE TABLE ci_persistence (value TEXT)"); '
                    '$db->exec("INSERT INTO ci_persistence VALUES (\'keep\')"); '
                    'if ($db->query("SELECT COUNT(*) FROM migrations")->fetchColumn() < 1) exit(1); '
                    'file_put_contents("storage/app/private/ci-proof.txt", "keep");')
        # Stop background writers before allowing the new app to run migrations.
        compose('stop')
        compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '180', '--pull', 'never')
        check_web()
        if MINIFILES:
            execute('python', '-c', 'from pathlib import Path; from backend.database import Database; '
                    'assert Database(Path("/config")).sections()[0]["name"] == "Keep"; '
                    'assert Path("/data/ci-proof.txt").read_text() == "keep"')
            assert certificate == (work / 'tls-data/caddy/pki/authorities/local/root.crt').read_bytes()
        else:
            execute('php', '-r', '$db = new PDO("sqlite:".getenv("DB_DATABASE")); '
                    'if ($db->query("SELECT value FROM ci_persistence")->fetchColumn() !== "keep") exit(1); '
                    'if (file_get_contents("storage/app/private/ci-proof.txt") !== "keep") exit(1);')
        print('Image-only install, web response and persistent data after recreation: passed.')
    except Exception:
        print(compose('logs', '--tail', '60'))
        raise
    finally:
        # This project name and all its volumes were created above for this test only.
        compose('down', '--volumes', '--remove-orphans')
        # On Linux, Caddy may create mode-700 child directories; the configured UID owns them.

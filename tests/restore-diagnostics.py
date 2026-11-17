"""Exercise the Hermes binary with disposable crypt remotes and a fixed destination."""
import os
import secrets
import subprocess
import sys
import time
import tempfile
from pathlib import Path

binary = sys.argv[1]


def cli(*args, **options):
    return subprocess.run([binary, *map(str, args)], capture_output=True, **options)


def configure(root, name, password, vault):
    secret = cli("obscure", "-", input=password.encode(), check=True).stdout.decode().strip()
    config = root / name
    # A stable object name makes a wrong content key reach authentication.
    config.write_text(f"[vault]\ntype = crypt\nremote = {vault}\n"
                      f"filename_encryption = off\npassword = {secret}\n")
    return config


def exercise_external_stop(root, config, original):
    # One controller serializes launches, revocation and publication for this job.
    root.mkdir()
    stage = root / "staging"
    stage.mkdir()
    partial = stage / "data"
    final = root / "restored"
    revoked = root / "revoked"
    launches = 0

    def launch(*options):
        nonlocal launches
        if revoked.exists():
            raise PermissionError("restore revoked")
        worker = subprocess.Popen([binary, "--config", str(config), "--inplace",
                                   "--local-no-preallocate", *options, "copyto",
                                   "vault:probe", str(partial)])
        launches += 1
        return worker

    def finish(worker):
        if worker.wait(timeout=10) == 0 and not revoked.exists():
            partial.replace(final)
        else:
            partial.unlink(missing_ok=True)

    # Positive control uses the same staging and publication path.
    finish(launch())
    assert final.read_bytes() == original.read_bytes()
    final.unlink()

    worker = launch("--bwlimit", "128k")
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            assert worker.poll() is None, "restore finished before stop"
            size = partial.stat().st_size if partial.exists() else 0
            if 0 < size < original.stat().st_size:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("no partial write observed")
        assert not final.exists()
        started = time.monotonic()
        revoked.touch(exist_ok=False)
        worker.terminate()
        finish(worker)
        elapsed = time.monotonic() - started
        assert worker.returncode != 0 and not final.exists()
        assert not list(stage.iterdir())
        try:
            launch()
        except PermissionError:
            pass
        else:
            raise AssertionError("revoked job restarted")
        assert launches == 2 and not final.exists() and not list(stage.iterdir())
        print(f"STOP PASS bytes={size} exit={worker.returncode} "
              f"seconds={elapsed:.3f} published=0 staged=0 retry_launches=0")
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


def exercise(root):
    approved = root / "restore" / "result"
    approved.parent.mkdir(mode=0o700)
    vault = root / "vault"
    good = configure(root, "good.conf", secrets.token_hex(32), vault)
    wrong = configure(root, "wrong.conf", secrets.token_hex(32), vault)
    original = root / "original"
    original.write_bytes(os.urandom(1024 * 1024))
    cli("--config", good, "copyto", original, "vault:probe", check=True)
    ciphertext, = vault.iterdir()
    reference = ciphertext.read_bytes()

    def restore(config, requested):
        # Private, single-writer directory. The caller can only select this literal target.
        if requested != str(approved):
            raise PermissionError("destination denied")
        with tempfile.TemporaryDirectory(dir=approved.parent) as stage:
            output = Path(stage) / "data"
            result = cli("--config", config, "--retries", 1, "--low-level-retries", 1,
                         "copyto", "vault:probe", output)
            if result.returncode:
                message = result.stderr.lower()
                if b"authenticat" not in message and b"bad block" not in message:
                    raise RuntimeError(f"unexpected restore error: {result.stderr!r}")
                return False
            output.replace(approved)
            return True

    outside = root / "outside"
    try:
        restore(good, str(outside))
    except PermissionError:
        assert not outside.exists() and not list(approved.parent.iterdir())
    else:
        raise AssertionError("outside destination accepted")
    print("Outside destination denied before staging or invoking copyto")

    assert not restore(wrong, str(approved))
    assert not approved.exists() and ciphertext.read_bytes() == reference
    assert restore(good, str(approved)) and approved.read_bytes() == original.read_bytes()
    print("Wrong key rejected; same ciphertext recovered byte-for-byte with original key")
    approved.unlink()

    damaged = bytearray(reference)
    damaged[-1] ^= 1
    ciphertext.write_bytes(damaged)
    assert not restore(good, str(approved)) and not list(approved.parent.iterdir())
    ciphertext.write_bytes(reference)
    assert restore(good, str(approved)) and approved.read_bytes() == original.read_bytes()
    print("Damaged ciphertext rejected; reference recovered byte-for-byte with same key")

    exercise_external_stop(root / "stop-test", good, original)


if not __debug__:
    raise RuntimeError("Run with assertions enabled")
os.umask(0o077)
with tempfile.TemporaryDirectory() as directory:
    exercise(Path(directory))

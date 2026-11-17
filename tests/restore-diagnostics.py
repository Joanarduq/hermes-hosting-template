"""Exercise the Hermes binary with disposable crypt remotes and a fixed destination."""
import os
import secrets
import subprocess
import sys
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


if not __debug__:
    raise RuntimeError("Run with assertions enabled")
os.umask(0o077)
with tempfile.TemporaryDirectory() as directory:
    exercise(Path(directory))

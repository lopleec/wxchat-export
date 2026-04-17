from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SQLCipherError(RuntimeError):
    pass


@dataclass(frozen=True)
class SQLCipherClient:
    binary: str

    def query_json(self, db_path: Path, key_hex: str, sql: str) -> list[dict]:
        script = "\n".join(
            [
                ".mode json",
                ".headers off",
                '.nullvalue ""',
                f'PRAGMA key = "x\'{key_hex}\'";',
                sql.strip(),
            ]
        )
        proc = subprocess.run(
            [self.binary, str(db_path)],
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = "\n".join(filter(None, [proc.stdout, proc.stderr])).strip()
        if proc.returncode != 0:
            raise SQLCipherError(combined or f"sqlcipher failed for {db_path}")

        stdout = proc.stdout.strip()
        if not stdout:
            return []
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SQLCipherError(combined or "Unexpected sqlcipher JSON output") from exc
        if isinstance(payload, list):
            return payload
        raise SQLCipherError("sqlcipher did not return a JSON array")

    def probe(self, db_path: Path, key_hex: str) -> None:
        self.query_json(
            db_path,
            key_hex,
            "SELECT COUNT(*) AS count FROM sqlite_master;",
        )

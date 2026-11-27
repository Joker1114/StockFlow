"""使用 SQLite Backup API 生成一致性备份。建议由系统定时器每天执行一次。"""
import argparse
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def backup(source: Path, output_dir: Path, keep: int = 7) -> Path:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = 'stockflow-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.db'
    result = output_dir / name
    temporary = output_dir / (name + '.tmp')
    try:
        with closing(sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise RuntimeError('备份文件完整性检查失败')
        temporary.replace(result)
    finally:
        temporary.unlink(missing_ok=True)
    for old in sorted(output_dir.glob('stockflow-*.db'), reverse=True)[keep:]:
        old.unlink()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(os.getenv('STOCKFLOW_DB_PATH', 'data/stockflow.db')))
    parser.add_argument('--output-dir', type=Path, default=Path('data/backups'))
    parser.add_argument('--keep', type=int, default=7)
    args = parser.parse_args()
    if args.keep < 1:
        parser.error('--keep 必须大于 0')
    print(backup(args.source, args.output_dir, args.keep))

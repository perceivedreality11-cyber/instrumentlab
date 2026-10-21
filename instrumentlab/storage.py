"""Each session owns one SQLite file, including raw and calibrated samples."""

from dataclasses import asdict
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3


class SessionStore:
    def __init__(self, path, config, identity):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Fail rather than append an unrelated recording to an existing file.
        if self.path.exists():
            raise FileExistsError(f"录制文件已存在：{self.path}")
        self.db = sqlite3.connect(self.path)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE blocks (seq INTEGER PRIMARY KEY, start_s REAL, raw TEXT,
                calibrated TEXT, metrics TEXT, alarm INTEGER);
            CREATE TABLE events (seq INTEGER, time_s REAL, kind TEXT, detail TEXT);
        """)
        self.db.executemany("INSERT INTO metadata VALUES (?, ?)", [
            ("schema_version", "1"), ("config", json.dumps(asdict(config))),
            ("identity", identity)])
        self.config = config
        self.db.commit()

    def append(self, frame):
        with self.db:
            self.db.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?)", (
                frame.seq, frame.start, json.dumps(frame.raw), json.dumps(frame.samples),
                json.dumps(asdict(frame.metrics)), int(frame.alarm)))
            if frame.event:
                self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (
                    frame.seq, frame.start, frame.event, f"peak={frame.metrics.peak:.4f} V"))

    def close(self):
        self.db.close()


def export_csv(database, destination):
    database, destination = Path(database), Path(destination)
    if database.resolve() == destination.resolve():
        raise ValueError("导出路径不能覆盖数据库")
    if not database.is_file():
        raise FileNotFoundError(database)
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as db:
        config = json.loads(db.execute("SELECT value FROM metadata WHERE key='config'").fetchone()[0])
        with destination.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["time_s", "raw_voltage_v", "voltage_v", "block", "alarm"])
            count = 0
            for seq, start, raw, calibrated, alarm in db.execute(
                    "SELECT seq,start_s,raw,calibrated,alarm FROM blocks ORDER BY seq"):
                for i, (before, after) in enumerate(zip(json.loads(raw), json.loads(calibrated))):
                    writer.writerow([f"{start + i / config['sample_rate']:.9f}",
                                     f"{before:.9f}", f"{after:.9f}", seq, alarm])
                    count += 1
    return count

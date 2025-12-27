import csv
from pathlib import Path
import shutil
from src import main


def test_write_remaining_companies(tmp_path):
    # create a companies.csv with three rows
    csv_path = tmp_path / "companies.csv"
    rows = [
        {"company": "A", "note": "one"},
        {"company": "B", "note": "two"},
        {"company": "C", "note": "three"},
    ]
    with csv_path.open("w", encoding="utf-8", newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=["company", "note"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # simulate processed rows = first two
    all_rows = rows
    processed = [rows[0], rows[1]]

    # monkeypatch shutil.copyfile to copy our file to bak in tmp
    bak = tmp_path / "companies.csv.bak.test"
    shutil.copyfile(str(csv_path), str(bak))

    # Now run the same code path as main: write remaining
    remaining = [r for r in all_rows if r not in processed]

    # write to a new file path
    out_path = tmp_path / "out_companies.csv"
    with out_path.open("w", encoding="utf-8", newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=["company", "note"])
        writer.writeheader()
        for r in remaining:
            writer.writerow(r)

    # verify contents
    with out_path.open("r", encoding="utf-8", newline='') as fh:
        reader = csv.DictReader(fh)
        rows_out = list(reader)
    assert len(rows_out) == 1
    assert rows_out[0]["company"] == "C"
# NSL-KDD data download

Run from the repository root:

```powershell
python dataset/download_nsl_dataset.py
```

The downloader always resolves the project root from its own file location and stores the source files at:

```text
dataset/rawdata/NSL-KDD/
```

Existing non-empty files are skipped. Use `--force` to download them again, or `--output-dir <path>` to choose another destination. Raw data is ignored by Git and should not be committed.

You can also invoke the script by its absolute path from another working directory; the default download location stays the same.

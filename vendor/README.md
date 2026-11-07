# vendor/ — Private wheels

| Package | Version | Source |
| :--- | :--- | :--- |
| `sammonny` | 1.8.6 | SamMonny Antidetect SDK (`sdk/python` of the SamMonny repo), not published on PyPI |

`requirements.txt` resolves it with `--find-links ./vendor`, so run pip from the repo root:

```powershell
pip install -r requirements.txt
```

## Updating the SDK

1. Bump `version` in the SDK's `sdk/python/pyproject.toml`.
2. Build the wheel into this folder (from the TAVM repo root):

   ```powershell
   python -m pip wheel --no-deps -w vendor <path-to-SamMonny>\sdk\python
   ```

3. Delete the old wheel, then update the pinned `sammonny==X.Y.Z` in `requirements.txt` and `pyproject.toml`.

## Developing the SDK side-by-side

To edit the SDK and TAVM at the same time, install the SDK editable on top of the pinned wheel:

```powershell
pip install -e <path-to-SamMonny>\sdk\python
```

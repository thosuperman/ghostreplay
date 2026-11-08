# Installation

GhostReplay needs Python 3.12 or newer. The SDK is not published on PyPI yet. Install it from the repository.

## From GitHub

```bash
pip install "ghostreplay @ git+https://github.com/thosuperman/ghostreplay@main#subdirectory=packages/ghostreplay"
```

With uv:

```bash
uv add "ghostreplay @ git+https://github.com/thosuperman/ghostreplay@main#subdirectory=packages/ghostreplay"
```

## From a local checkout

```bash
git clone https://github.com/thosuperman/ghostreplay.git
pip install ./ghostreplay/packages/ghostreplay
```

## From a built wheel

```bash
cd ghostreplay
uv build packages/ghostreplay --out-dir dist      # or: python -m build packages/ghostreplay
pip install dist/ghostreplay-0.1.0-py3-none-any.whl
```

## Extras

| Install | Adds | When you need it |
|---|---|---|
| `ghostreplay` | `pydantic` | Always. The SDK, CLI, replay engine and regression runner. |
| `ghostreplay[server]` | `fastapi`, `uvicorn` | The HTTP API and dashboard backend (`ghostreplay serve`, the bundled labs) |
| `ghostreplay[live]` | `anthropic` | The built-in Anthropic model adapter for live LLM calls |

## Check the install

```bash
python -c "import ghostreplay; print(ghostreplay.__version__)"
ghostreplay --help
```

Installing the SDK into a fresh virtual environment, together with the separate invoice example, is verified in CI (the `sdk` job in `.github/workflows/ci.yml`). That check confirms `fastapi` is not imported.

# Gemini Agent for OCI Hosted Deployment

A minimal FastAPI service that sends prompts to the Gemini Developer API through the Google Gen AI Python SDK. `main.py` uses `GEMINI_MODEL` (default: `gemini-flash-latest`) and starts Uvicorn on `0.0.0.0:8080` by default.

## Current implementation

| Item | Behavior |
| --- | --- |
| Invocation | `POST /invoke` with `{"prompt":"..."}` |
| Response | JSON with a `response` field |
| Health probe | `GET /health` returns `{"status":"healthy"}` |
| API documentation | `/docs` |
| Chat history | One shared, in-memory Gemini chat per application process |
| Streaming | Not implemented |
| Container | `python:3.13-slim`, working directory `/app`, command `python main.py` |

The chat is created when the module is imported and reused for every invocation. Requests share conversation history, including across callers, and restarting the process clears that history. There is no per-user session isolation or authentication in the application.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | FastAPI endpoints, Gemini client, and Uvicorn entry point |
| `Dockerfile` | Installs locked dependencies with `uv`, copies `main.py`, and exposes port 8080 |
| `pyproject.toml` | Project metadata and runtime dependencies; requires Python 3.13+ |
| `uv.lock` | Locked dependencies for `uv` |
| `.python-version` | Selects Python 3.13 for local tooling |
| `.env.example` | Configuration template |
| `.dockerignore` | Excludes local environment files, credentials, and caches from the build context |

## Local setup

Use Python 3.13+ and `uv`. Copy the configuration template if you do not already have a `.env` file:

```bash
cp .env.example .env
```

Set your Gemini API key in `.env`:

```dotenv
GEMINI_API_KEY=your-gemini-api-key
PORT=8080
```

`GEMINI_API_KEY` is required. The application raises a `RuntimeError` during import if it is missing or empty, so the service and its health endpoint will not start. `load_dotenv()` loads a local `.env` file; values in `.env` override existing environment variables (`override=True`).

`PORT` is optional and defaults to `8080` when running `python main.py`. `GEMINI_MODEL` selects the model and defaults to `gemini-flash-latest`. `LOG_LEVEL` in `.env.example` is not read by the application.

Install dependencies and start the service:

```bash
uv sync --locked
uv run python main.py
```

Open <http://localhost:8080/docs> for interactive API documentation.

## Test the endpoints

Check service health:

```bash
curl -i http://localhost:8080/health
```

Expected body:

```json
{"status":"healthy"}
```

The health endpoint does not contact Gemini or verify that the key can successfully generate a response. There is no separate `/ready` endpoint; use `/health` for HTTP probes.

Invoke the agent:

```bash
curl -sS -X POST http://localhost:8080/invoke \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the capital of Bhutan?"}'
```

Example response (wording may vary):

```json
{"response":"The capital of Bhutan is Thimphu."}
```

Subsequent prompts use the same shared chat history. A system instruction requests one short sentence on a single line for every prompt, including requests for longer answers. The API also removes line breaks from returned text. Sentence brevity depends on model adherence; no language instruction is imposed.

| Result | Behavior |
| --- | --- |
| HTTP `200` | Successful invocation, returning Gemini's `response.text` (which may be null) |
| HTTP `422` | Request does not match the required `prompt: str` schema |
| HTTP `500` | Exception during generation; its string is returned in `detail` |
| Startup failure | Missing/empty API key or another initialization error |

There is no explicit non-blank validation or length limit on `prompt`.

## Container build and run

The Dockerfile uses Python 3.13 and copies the pinned `uv` binary from its official image. It copies `pyproject.toml` and `uv.lock`, then runs:

```dockerfile
RUN uv sync --locked --no-dev --no-install-project --no-cache
```

This installs runtime dependencies into `/app/.venv` and checks that the lockfile matches the project. No `requirements.txt` is needed. The project itself is not installed as a package because the container runs `main.py` directly. Dependency installation is cached independently of application code changes.

`ENV PATH="/app/.venv/bin:$PATH"` makes `CMD ["python", "main.py"]` use the virtual environment's Python. Dependencies are installed at build time; startup does not need to run `uv sync` again.

When changing dependencies, use `uv add <package>` (or update `pyproject.toml` and run `uv lock`), keep `uv.lock` with the project, and rebuild the image.

The Dockerfile does not configure a non-root user or a Docker `HEALTHCHECK`.

Build and run:

```bash
docker buildx build --platform linux/amd64 --load -t oci-gemini-agent:v1 .

docker run --rm -p 8080:8080 --env-file .env oci-gemini-agent:v1
```

The image copies only `main.py` as application code; `.env` is supplied at runtime. If you change `PORT`, adjust the container-side port mapping and deployment port accordingly. `EXPOSE 8080` is image metadata and does not override `PORT`.

## Deployment configuration

After building the container, push the image to your chosen container registry and configure your hosting environment with:

- The container image and its required registry access.
- `GEMINI_API_KEY` supplied at runtime.
- Application port `8080` (or the configured `PORT`).
- HTTP health/readiness probe path `/health`.
- Outbound HTTPS access to the Gemini Developer API.
- Invocation routing to `POST /invoke` with the `prompt` JSON field.

Configure inbound access controls in the hosting environment: the application itself does not authenticate callers. Account for the shared chat history when choosing who can access a deployment.

These are application settings inferred from the source; deployment compatibility with a specific OCI hosting service must be checked against that service's contract.

Dependency installation follows the [official uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/).

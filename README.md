# OCI Hosted Deployment — Minimal Gemini Agent

A stateless FastAPI service that calls the Gemini Developer API through Google's Python SDK. OCI hosts the container; Gemini generates the answer. A system instruction requests one short sentence, and whitespace normalization keeps the **returned text on one line**. Each request is independent, with no stored conversation history or language-specific instruction; brevity depends on model adherence.

## Service and files

| Item | Implementation |
| --- | --- |
| API | `POST /chat` with `{"prompt":"..."}`; JSON answer in `response` |
| SSE | `Accept: text/event-stream` returns one `completed` event after generation |
| Readiness | `GET /ready`: `200` when the client is initialized, otherwise `503` |
| Liveness | `GET /health`: `200` |
| Probes | Empty body, `Content-Type: application/json`; no Gemini call or key validation |
| Runtime | Uvicorn on `0.0.0.0:8080`; `CMD ["python", "main.py"]` |
| Container | `python:3.13-slim`, Linux x86_64 (`linux/amd64`), non-root UID 1000 |
| Filesystem | Read-only root supported; home, temporary files, and caches use writable `/tmp` |

| File | Purpose |
| --- | --- |
| `main.py` | Gemini calls, probes, JSON/SSE responses, and one-line normalization |
| `requirements.txt` | Five direct runtime dependencies; `pip` installs their dependencies automatically |
| `Dockerfile`, `.dockerignore` | Image definition; build context limited to Dockerfile, requirements, and application code |
| `.env.example`, `.python-version` | Configuration template and Python 3.13 selection |
| `tests/test_main.py` | Probe, lifecycle, validation, normalization, and response-format checks |

## 1. Configure the Gemini API key

Create a key in [Google AI Studio](https://aistudio.google.com/app/api-keys), then copy the template (or edit your existing `.env`):

```bash
cp .env.example .env
```

```dotenv
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-flash-latest
```

`GEMINI_API_KEY` is required; a missing/empty key prevents startup. `GEMINI_MODEL` is optional and defaults to `gemini-flash-latest`; choose a model available to your project. Local `.env` values override existing environment variables (`load_dotenv(override=True)`).

The real `.env` is excluded from Git and the image. Supply credentials at runtime, keeping them out of source code, build arguments, and image tags. Do not set OCI-reserved variables such as `PORT`, `K_SERVICE`, or `OCI_RESOURCE_PRINCIPAL_*`; the service uses port `8080`.

### Optional: run locally without Docker

With Python 3.13+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py

"Test locally
curl -i http://localhost:8080/ready
curl -i http://localhost:8080/health

curl -sS -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the capital of Spain?"}'
```

Interactive API documentation: <http://localhost:8080/docs>.

## 2. Docker | Build the container

```bash
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  --load -t oci-gemini-agent:v1 .
```

For this test image, `--provenance=false --sbom=false` disables build attestations that can otherwise appear as extra digest-only entries in OCIR. Existing entries remain after rebuilding; they are not additional application versions. See [Docker build attestations](https://docs.docker.com/build/metadata/attestations/).

Python is included in the base image; no OS package installation or separate Python download is needed. Docker installs dependencies using `pip install --no-cache-dir -r requirements.txt`. `uv` is not used; `uvicorn` serves FastAPI. Installation happens at build time, and Docker reuses the dependency layer when only `main.py` changes.

Keep dependency versions in `requirements.txt`; after changes, install, test, and rebuild. The image disables bytecode writes and pip version checks. OCI uses the HTTP probes; no Docker `HEALTHCHECK`, persistent conversation storage, or volume mapping is needed.

## 3. Docker | Test locally

```bash
docker run --rm -p 8080:8080 --env-file .env oci-gemini-agent:v1
```

In another terminal:

```bash
curl -i http://localhost:8080/ready
curl -i http://localhost:8080/health

curl -sS -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the capital of Malaysia?"}'
```

Example answer (wording may vary):

```json
{"response":"The capital of Malaysia is Kuala Lumpur."}
```

For SSE:

```bash
curl -N -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"prompt":"What is the capital of Bhutan?"}'
```

```text
event: completed
data: {"response": "The capital of Bhutan is Thimphu."}

```

JSON and SSE use the same normalized answer. SSE sends the full answer as one event, without intermediate Gemini tokens. Generation failures occur before SSE starts and return JSON with HTTP `502`. Each generation uses the same system instruction and a 60-second SDK HTTP timeout.

## 4. Push to Oracle Container Registry

Create a repository in OCI Console, for example `repo-oci-gemini-agent`, then replace the registry, namespace, and repository (with repo-oci-gemini-agent) placeholders:

```bash
docker login <region-key>.ocir.io
docker tag oci-gemini-agent:v1 <region-key>.ocir.io/<tenancy-namespace>/<repository>:v1
docker push <region-key>.ocir.io/<tenancy-namespace>/<repository>:v1
```

For Ashburn, use `iad.ocir.io`. Example image path: `iad.ocir.io/<tenancy-namespace>/repo-oci-gemini-agent:v1`. Use the login details for your tenancy and region; supply the Gemini key separately at runtime.

## 5. Deploy and invoke on OCI

1. Create Generative AI application (if note exists)
2. Go to Configuration tab and add Environment variable for `GEMINI_API_KEY` and optionally `GEMINI_MODEL` 
3. Go to Deployment and create a deployment using the pushed OCIR image.
4. Allow outbound HTTPS to `generativelanguage.googleapis.com`, use port `8080`, and confirm `/ready` and `/health` succeed.
5. Wait for the deployment to become active. Copy the Console-provided application endpoint and append `/chat`: the final path is **`/actions/invoke/chat`**.

Match authentication to the application: Default applications use `hostedApplications` with an identity-domain bearer token; OCI IAM applications use `hostedApplicationsIam` with OCI request signatures. Use the Console endpoint without manually changing its resource type. See [OCI invocation guidance](https://docs.oracle.com/en-us/iaas/Content/generative-ai/use-applications.htm).

### 5.1 Test

**Example API Endpoint:** https://inference.generativeai.<region>.oci.oraclecloud.com/20251112/hostedApplications/<hosted_app_ocid>/actions/invoke/**<custom_path>**

** **<custom_path>** to be replaced by **health | ready | chat**

**5.1.1** 

If the application has **Authentication type: No Authentication** 

```bash
curl -i '<console-application-endpoint-ending-in-actions/invoke>/health' \
	
curl -N -X POST '<console-application-endpoint-ending-in-actions/invoke>/chat' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"prompt":"What is the capital of Luxembourg?"}'
```

**5.1.2**

For an OCI IAM application with API-key request signing:

```bash
oci raw-request \
  --profile DEFAULT \
  --auth api_key \
  --http-method POST \
  --target-uri '<console-application-endpoint-ending-in-actions/invoke>/chat' \
  --request-headers '{"content-type":"application/json"}' \
  --request-body '{"prompt":"What is the capital of Bangladesh?"}'
```

Use any sample prompt from section 3. Inbound OCI credentials are separate from the outbound `GEMINI_API_KEY`.

**HTTP 404 (`{"detail":"Not Found"}`):** check that the URL ends in `/actions/invoke/chat`; `/actions/invoke` alone can reach the undefined container root. If the deployed image already exposes `/chat`, fix only the request URL. After changing a route, rebuild, push a new image tag, and activate its deployment. The authenticated `/actions/invoke/docs` URL shows deployed API routes.

## References

- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)
- [OCI container requirements](https://docs.oracle.com/en-us/iaas/Content/generative-ai/prepare-artifacts.htm)
- [OCI hosted applications and deployments](https://docs.oracle.com/en-us/iaas/Content/generative-ai/applications-deployments.htm)

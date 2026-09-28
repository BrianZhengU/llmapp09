# llmapp09 – CI/CD for the projects

The llmapp08 app (with guardrails), packaged and shipped as an end-to-end LLMOps pipeline:

```
llmapp09/
├── .github/workflows/
│   ├── llm-multiroute-ci.yaml        unit tests → build → Trivy scan → push to Docker Hub (amd64+arm64)
│   ├── llm-frontend-python-ci.yaml   smoke test → build → Trivy scan → push to Docker Hub
│   ├── promptfoo-tests.yaml          start API on Ollama Cloud → promptfoo eval
│   └── deepeval-tests.yaml           start API → DeepEval (judge tests only if OPENAI_API_KEY is set)
├── docker-compose.yml                both services on one Docker network
├── llm-multiroute/                   API  (Dockerfile, build.sh, k8s/deployment.yaml, tests/)
├── llm-frontend-python/              UI   (Dockerfile, build.sh, k8s/deployment.yaml)
├── promptfoo-tests/
└── deepeval-tests/
```

## 1. Run locally without containers

Same as llmapp08: see the top-level README.

## 2. Docker network (docker compose)

```bash
cp llm-multiroute/.env.template llm-multiroute/.env   # add OLLAMA_API_KEY etc.
docker compose up -d --build
# frontend http://localhost:5000   API http://localhost:8080/swagger-ui.html
docker compose logs -f llm-multiroute
docker compose down
```

Secrets are read from `.env` at runtime and never copied into images (see `.dockerignore`).

## 3. Scan an image for vulnerabilities (Trivy)

```bash
brew install aquasecurity/trivy/trivy        # or: docker run aquasec/trivy ...
trivy image --severity HIGH,CRITICAL llm-multiroute:local
```

In CI this runs automatically. Set `TRIVY_EXIT_CODE: "1"` in the workflow to fail the build on findings.

## 4. minikube

Build and push images first (CI does this, or use `build.sh` for reference):

```bash
cd llm-multiroute && DOCKERHUB_USERNAME=<your-id> ./build.sh 1.0.0
```

In both `k8s/deployment.yaml` files, replace `your-dockerhub-id` with your Docker Hub account ID. Then:

```bash
minikube start

# Terminal/Shell 1 (llmapp09 root)
cd llm-multiroute && kubectl apply -f ./k8s/deployment.yaml
kubectl -n llm-multiroute-backend create secret generic llm-multiroute-secrets \
  --from-literal=OLLAMA_API_KEY=<key>
kubectl rollout restart deploy/llm-multiroute-app -n llm-multiroute-backend
kubectl port-forward svc/llm-multiroute-service -n llm-multiroute-backend 8080

# Terminal/Shell 2 (llmapp09 root)
cd llm-frontend-python && kubectl apply -f ./k8s/deployment.yaml
kubectl port-forward svc/llm-frontend-service -n llm-frontend 5000
```

Without Docker Hub, build straight into minikube: `eval $(minikube docker-env)`, then `docker build -t your-dockerhub-id/llm-multiroute:1.0.0 llm-multiroute`.

Troubleshooting:

```bash
kubectl replace --force -f ./k8s/deployment.yaml
kubectl get po -A
k get deploy -A                      # alias k=$(which kubectl)
k logs -f deploy/llm-multiroute-app -n llm-multiroute-backend
kubectl describe pod -n llm-multiroute-backend   # ImagePullBackOff? check the image name
```

## 5. GitHub + GitHub Actions

1. In `.github/workflows/llm-multiroute-ci.yaml` and `llm-frontend-python-ci.yaml`, set `DOCKERHUB_USERNAME: your-dockerhub-id` in the `env:` block.
2. Create a Docker Hub token: docker.com → Settings → Personal Access Tokens → Generate New Token (Read & Write). Copy it; it's shown only once.
3. Push this folder as its own repo:

```bash
cd llmapp09
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/<your GitHub username>/llmapp09
git remote -v
git branch -m main
git push -u origin main
```

4. On GitHub, go to Settings → Secrets and variables → Actions and add these **repository secrets**:

| Secret | Used by |
|---|---|
| `DOCKERHUB_TOKEN` | image push |
| `OLLAMA_API_KEY` | promptfoo / DeepEval runs (API calls Ollama Cloud) |
| `OLLAMA_BASE_URL` | optional, defaults to `https://ollama.com` |
| `OPENAI_API_KEY` | optional: DeepEval judge for summarize/toxicity/bias/hallucination |

Pushes to `main` run the pipelines whose paths changed. Pull requests test and scan but don't push images. Every workflow can also be started by hand (Actions → *workflow* → Run workflow).

## References

- https://medium.com/@ravipatel.it/automating-docker-image-creation-and-push-to-docker-hub-for-a-react-app-using-github-actions-7fa092751fc0
- https://medium.com/@vincenthartmann/how-to-add-a-security-scan-with-trivy-in-github-actions-8f16642aa82b
- https://docs.digitalocean.com/products/kubernetes/how-to/deploy-using-github-actions/

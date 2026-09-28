#!/usr/bin/env bash
# Build and push the frontend image to Docker Hub (reference - CI does this for you).
# Usage: DOCKERHUB_USERNAME=<your-id> ./build.sh [version]
set -euo pipefail
DOCKER_USER="${DOCKERHUB_USERNAME:?set DOCKERHUB_USERNAME to your Docker Hub account ID}"
VERSION="${1:-1.0.0}"
IMAGE="$DOCKER_USER/llm-frontend-python:$VERSION"

# Apple Silicon / ARM
docker build --platform linux/arm64 -t "$IMAGE" .
docker push "$IMAGE"

# Intel / AMD (overwrites the tag above - keep the one matching your cluster), or build both:
#   docker buildx build --platform linux/amd64,linux/arm64 -t "$IMAGE" --push .
# docker build --platform=linux/amd64 -t "$IMAGE" .
# docker push "$IMAGE"

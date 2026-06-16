.DEFAULT_GOAL := help

# Override on the command line: make deploy-dev DOMAIN=prod.example.com IMAGE_TAG=abc1234
DOMAIN ?= website.dn.womblelabs.co.uk
IMAGE_TAG ?= latest

.PHONY: help install dev dev-stop dev-logs dev-build dev-clean \
        build check-build watch lint format test synth deploy-dev new-env smoke

help:
	@echo "Local dev"
	@echo "  install    Install Python dependencies via uv"
	@echo "  dev        Start all local services (Ghost + MySQL + nginx)"
	@echo "  dev-stop   Stop all local services"
	@echo "  dev-logs   Tail Ghost logs"
	@echo "  dev-build  Rebuild Docker images (run after Dockerfile/theme changes)"
	@echo "  dev-clean  Remove containers, volumes, and local images"
	@echo "  build      Regenerate templates + assets (CSS) from frontend/ source"
	@echo "  watch      Rebuild frontend on save; theme is bind-mounted so just refresh"
	@echo "  lint       Run ruff check + frontend build drift check"
	@echo "  format     Run ruff format (auto-fix)"
	@echo "  test       Run pytest"
	@echo ""
	@echo "Deployment"
	@echo "  new-env    Write SSM parameters for a new environment (run once per account)"
	@echo "  synth      Synthesise CloudFormation templates"
	@echo "  deploy-dev Deploy all stacks to dev account"
	@echo "  smoke      Run smoke tests against URL=<url>"

install:
	uv sync --all-groups

dev:
	docker compose up -d
	@echo ""
	@echo "Ghost is starting at http://localhost:8080"
	@echo "First run: visit http://localhost:8080/ghost/ to complete setup,"
	@echo "then go to Settings → Design → Activate to enable the dn-theme."

dev-stop:
	docker compose down

dev-logs:
	docker compose logs -f ghost

dev-build:
	docker compose build

dev-clean:
	docker compose down -v --rmi local

build:
	uv run python frontend/build.py

check-build:
	uv run python frontend/build.py --check

watch:
	uv run python frontend/watch.py

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run python frontend/build.py --check

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest tests/ -v

synth:
	cdk synth -c domain=$(DOMAIN)

deploy-dev:
	cdk deploy --all --require-approval never -c domain=$(DOMAIN) -c imageTag=$(IMAGE_TAG)

new-env:
	uv run python scripts/new_env.py

smoke:
	SMOKE_URL=$(URL) uv run pytest tests/smoke/ -v

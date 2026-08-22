.PHONY: contracts-test contracts-check contracts-codegen \
        api-db-up api-db-down api-migrate api-test api-run e2e

PYTHON ?= python3
API_DIR := services/control-api
CONTRACTS_SCHEMAS := packages/contracts/schemas/v1
GENERATED := $(API_DIR)/app/contracts/v1
DATABASE_URL ?= postgresql+asyncpg://control:control@localhost:55432/control_test

contracts-test:
	$(PYTHON) -m unittest discover -s packages/contracts/tests -p 'test_*.py' -v

contracts-check: contracts-test
	$(PYTHON) -m json.tool packages/contracts/state-machine/v1.json >/dev/null
	$(PYTHON) -m json.tool packages/contracts/examples/v1/manifest.json >/dev/null

# Regenera os modelos Pydantic a partir dos JSON Schemas versionados.
# Fonte unica de verdade: nenhuma regra de validacao e reescrita a mao em Python.
contracts-codegen:
	rm -rf $(GENERATED)
	$(PYTHON) -m datamodel_code_generator \
	  --input $(CONTRACTS_SCHEMAS) \
	  --input-file-type jsonschema \
	  --output $(GENERATED) \
	  --output-model-type pydantic_v2.BaseModel \
	  --target-python-version 3.11 \
	  --use-standard-collections \
	  --use-union-operator \
	  --enum-field-as-literal one \
	  --disable-timestamp \
	  --field-constraints \
	  --formatters black

api-db-up:
	docker compose -f $(API_DIR)/docker-compose.test.yml up -d --wait

api-db-down:
	docker compose -f $(API_DIR)/docker-compose.test.yml down -v

api-migrate:
	cd $(API_DIR) && DATABASE_URL=$(DATABASE_URL) $(PYTHON) -m alembic upgrade head

api-test:
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) -m pytest $(API_DIR)/tests -q

api-run:
	cd $(API_DIR) && $(PYTHON) -m uvicorn app.main:app --reload --port 8000

e2e:
	./tests/e2e/run.sh

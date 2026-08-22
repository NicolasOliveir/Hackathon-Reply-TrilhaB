.PHONY: contracts-test contracts-check

contracts-test:
	python3 -m unittest discover -s packages/contracts/tests -p 'test_*.py' -v

contracts-check: contracts-test
	python3 -m json.tool packages/contracts/state-machine/v1.json >/dev/null
	python3 -m json.tool packages/contracts/examples/v1/manifest.json >/dev/null

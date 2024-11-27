install:
	pip install -r requirements.txt
	pre-commit install

fix-format:
	-ruff check --fix
	-ruff format
	-ruff check --fix
	-ruff format

fix-format-noqa:
	-ruff check --fix
	-ruff format
	-ruff check --fix
	-ruff check --add-noqa
	-ruff format
	-ruff check --fix
	-ruff check --add-noqa
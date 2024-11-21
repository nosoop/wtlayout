test:
  ruff check src

format:
  ruff check src --select I001 --fix
  ruff format src

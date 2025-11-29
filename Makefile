.PHONY: install ingest list start stats archive clean

install:
	python3 -m pip install -r requirements.txt

run:
	python3 main.py

ingest:
	python3 main.py ingest "$(MSG)"

list:
	python3 main.py list

start:
	python3 main.py start $(ID)

stats:
	python3 main.py stats

archive:
	python3 main.py archive

clean:
	rm -rf __pycache__

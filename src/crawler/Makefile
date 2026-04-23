.PHONY: install test collect validate clean report

# Installation
install:
	pip install -r requirements.txt
	python -m nltk.downloader punkt stopwords
	python -m spacy download en_core_web_sm

install-dev:
	pip install -e .
	pip install pytest black flake8 mypy

# Data collection
collect:
	python main.py --config config.yaml

collect-so:
	python main.py --config config.yaml --platforms stackoverflow

collect-reddit:
	python main.py --config config.yaml --platforms reddit

collect-github:
	python main.py --config config.yaml --platforms github

collect-zenodo:
	python main.py --config config.yaml --platforms zenodo

collect-devto:
	python main.py --config config.yaml --platforms devto

collect-hashnode:
	python main.py --config config.yaml --platforms hashnode

collect-hn:
	python main.py --config config.yaml --platforms hackernews

collect-lobsters:
	python main.py --config config.yaml --platforms lobsters

collect-gitlab:
	python main.py --config config.yaml --platforms gitlab

collect-tier2:
	python main.py --config config.yaml --platforms devto,hashnode,hackernews,lobsters,gitlab

# Validation
validate:
	python -c "from tools.data_validator import DataValidator; v = DataValidator(); r = v.validate_dataset('output/combined_analogies_*.csv'); v.generate_validation_report(r, 'output/validation_report.txt')"

# Analysis
report:
	python -c "from tools.survey_collector import SurveyCollector; s = SurveyCollector(); s.generate_report()"

# Testing
test:
	pytest tests/ -v

lint:
	black . --include "\\.py$$"
	flake8 . --max-line-length=100

# Cleanup
clean:
	rm -rf output/*.csv
	rm -rf logs/*.log
	rm -rf __pycache__
	rm -rf *.pyc
	rm -rf .pytest_cache

# Help
help:
	@echo "Available targets:"
	@echo "  install      - Install dependencies"
	@echo "  collect      - Run full data collection"
	@echo "  collect-so   - Collect from Stack Overflow only"
	@echo "  collect-reddit   - Collect from Reddit only"
	@echo "  collect-github   - Collect from GitHub only"
	@echo "  collect-devto    - Collect from DEV Community"
	@echo "  collect-hashnode - Collect from Hashnode"
	@echo "  collect-hn       - Collect from Hacker News"
	@echo "  collect-lobsters - Collect from Lobsters"
	@echo "  collect-gitlab   - Collect from GitLab"
	@echo "  collect-tier2    - Collect from all Tier-2 sources"
	@echo "  validate     - Validate collected data"
	@echo "  report       - Generate survey report"
	@echo "  test         - Run test suite"
	@echo "  lint         - Format and lint code"
	@echo "  clean        - Remove generated files"
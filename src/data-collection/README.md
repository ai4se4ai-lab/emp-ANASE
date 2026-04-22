pip install -r requirements.txt
cp .env.example .env          # fill in your API keys
python collect_data.py --demo # test pipeline immediately (no keys needed)
python collect_data.py        # full live collection
python collect_data.py --platforms stackoverflow,github --max-results 500
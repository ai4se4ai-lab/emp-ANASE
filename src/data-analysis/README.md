# Step 1: Collect
python collect_data.py --demo           # or remove --demo with real API keys

# Step 2: Analyse
python analysis.py --input output/combined_dataset.csv

# Step 3: Visualize
python visualize.py --input output/err_scatter_data.csv
from setuptools import setup, find_packages

setup(
    name="analogical-reasoning-collector",
    version="1.0.0",
    description="Data collection framework for analogical reasoning in agentic software engineering research",
    author="Anonymous Authors",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "pyyaml>=6.0.1",
        "pandas>=2.0.0",
        "tqdm>=4.66.0",
        "python-dotenv>=1.0.0",
        "praw>=7.7.0",
        "nltk>=3.8.1",
        "spacy>=3.7.0",
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "analogy-collect=main:main",
        ],
    },
)
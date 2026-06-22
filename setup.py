from setuptools import setup, find_packages

setup(
    name="preserve",
    version="0.3.0",
    description="Privacy-preserving PII detection and scrubbing for LLM inference queries",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "openai>=1.0.0",
        "pydantic>=2.0",
        "python-dotenv>=1.0.0",
        "phonenumbers>=9.0.0",
        "email-validator>=2.0.0",
        "dateparser>=1.0.0",
        "names-dataset>=3.0.0",
        "wordfreq>=3.0.0",
    ],
    extras_require={
        "ner": ["spacy>=3.0"],
        "llm": ["llama-cpp-python>=0.2.0"],
        "api": ["fastapi>=0.110", "uvicorn>=0.27"],
        "redis": ["redis>=5.0"],
        "all": ["spacy>=3.0", "llama-cpp-python>=0.2.0", "fastapi>=0.110", "uvicorn>=0.27", "redis>=5.0"],
        "dev": ["pytest>=7.0", "pytest-mock>=3.0", "huggingface-hub", "httpx"],
    },
)

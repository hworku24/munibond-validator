from setuptools import setup, find_packages

setup(
    name="munibond-validator",
    version="1.0.0",
    description="Data quality validation engine for structured financial datasets",
    author="Agapi Gessesse",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
        "rich>=13.0.0",
        "jinja2>=3.1.0",
    ],
    entry_points={
        "console_scripts": [
            "munibond-validate=munibond_validator.main:main",
        ],
    },
    python_requires=">=3.9",
)

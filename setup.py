from setuptools import setup, find_packages

setup(
    name="agent-memory-forge",
    version="1.0.0",
    description="Unified agent memory system with git-like versioning, compression, and semantic search",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="gardvori",
    author_email="gardvori@users.noreply.github.com",
    url="https://github.com/gardvori/agent-memory-forge",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
        "rich>=13.0",
        "sqlite-vec>=0.1.0",
        "numpy>=1.24.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "pytest-cov>=4.0"],
        "embeddings": ["sentence-transformers>=2.0"],
    },
    entry_points={
        "console_scripts": [
            "amf=agent_memory_forge.cli:main",
            "agent-memory-forge=agent_memory_forge.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)

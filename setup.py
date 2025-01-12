from setuptools import setup, find_packages

setup(
    name="SynAnno",
    version="0.1.0",
    description="A package for annotation processing and cloud volume handling.",
    author="Leander Lauenburg",
    author_email="leander.lauenburg@gmail.com",
    url="https://github.com/PytorchConnectomics/SynAnno",
    packages=find_packages(),
    install_requires=[
        "cloud-volume",
        "flask>=2.3.2",
        "flask-cors>=4.0.0",
        "flask-session>=0.5.0",
        "imageio>=2.31.1",
        "networkx>=3.1",
        "neuroglancer>=2.36",
        "numpy<2",
        "oauth2client>=4.1.3",
        "opencv-python>=4.7.0.72",
        "pandas>=2.0.3",
        "scikit-image>=0.21.0",
        "scipy>=1.11.0",
        "tifffile>=2023.4.12",
        "fpzip==1.2.4",
        "python-dotenv==1.0.1",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pre-commit",
        ],
        "seg": [
            "torch",
            "torchvision",
            "torchsummary",
            "tqdm",
            "matplotlib",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

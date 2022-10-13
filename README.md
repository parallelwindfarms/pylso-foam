---
title: pylso-foam
subtitle: Python module for Large Scale Orchestration of OpenFoam computations.
author: Johan Hidding, Pablo Rodríguez Sanchez
---
[![Entangled badge](https://img.shields.io/badge/entangled-Use%20the%20source!-%2300aeff)](https://entangled.github.io/)

This module lets you interact with OpenFOAM through Python. You may use it in cases where you need to run a lot of separate computations in OpenFOAM, possibly in parallel. In our view, this fixes a few gaps in the PyFoam module. Here's what `pylso-foam` can and `PyFoam` can't do:

- Run jobs in parallel: PyFoam has a lot of hidden state. In `pylso-foam` every job runs in its own case directory.
- Work with binary OpenFOAM files: by using the [`byteparsing`](https://parallelwindfarms.github.io/byteparsing) package, we can interact with binary data. We don't involve any geometry here, we can just read the raw data and do some arithmetic on it.

# Admin
You may `pip install` this module. If you're developing however, we use `poetry` to manage dependencies.

# License
Apache 2


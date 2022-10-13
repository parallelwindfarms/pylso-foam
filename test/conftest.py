import pytest
import os


def pytest_configure(config):
    if "FOAM_API" not in os.environ or os.environ["FOAM_API"] == "":
        pytest.exit("OpenFOAM needed to run tests.")

import os
import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

@pytest.fixture
def fx():
    return lambda name: os.path.join(FIXTURES, name)

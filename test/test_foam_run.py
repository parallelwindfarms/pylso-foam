# ~\~ language=Python filename=test/test_foam_run.py
# ~\~ begin <<lit/testing.md|test/test_foam_run.py>>[init]
from pathlib import Path
from shutil import copytree
import numpy as np

from pylsoFoam.vector import BaseCase
from pylsoFoam.foam import (block_mesh, foam)

pitzDaily_fields = {
    "T", "U", "phi"
}

def test_basic_pitzDaily(tmp_path):
    path = Path(tmp_path) / "case0"
    data = Path(".") / "test" / "cases" / "pitzDaily"
    copytree(data, path / "base")

    base_case = BaseCase(path, "base")
    base_case.fields = pitzDaily_fields
    block_mesh(base_case)

    base_vec = base_case.new_vector()
    init_vec = foam("scalarTransportFoam", 0.001, base_vec, 0.0, 0.001)
    # init_vec.time = "0"
    end_vec = foam("scalarTransportFoam", 0.01, init_vec, 0.001, 0.1)

    assert end_vec.dirname.exists()

    end_vec_clone = end_vec.clone()
    assert end_vec_clone.time == end_vec.time
    # assert get_times(end_vec_clone.path) == ["0", "0.1"]

    diff_vec = end_vec - init_vec

    for f in pitzDaily_fields:
        with end_vec.mmap_data(f) as a, \
             init_vec.mmap_data(f) as b, \
             diff_vec.mmap_data(f) as c:
            assert np.abs(a() - b() - c()).mean() < 1e-6

    # assert diff_vec.time == "0.1"
    orig_vec = init_vec + diff_vec
    should_be_zero = end_vec - orig_vec
    for f in pitzDaily_fields:
        with should_be_zero.mmap_data(f) as v:
            assert np.all(np.abs(v()) < 1e-6)


def test_restart(tmp_path):
    path = Path(tmp_path) / "case0"
    data = Path(".") / "test" / "cases" / "pitzDaily"
    copytree(data, path / "base")

    base_case = BaseCase(path, "base")
    base_case.fields = pitzDaily_fields
    block_mesh(base_case)

    init_vec = base_case.new_vector()
    check = foam("scalarTransportFoam", 0.01, init_vec, 0.0, 0.2)
    end_vec = foam("scalarTransportFoam", 0.01, init_vec, 0.0, 0.1)
    init_vec = end_vec.clone()
    end_vec = foam("scalarTransportFoam", 0.01, init_vec, 0.1, 0.2)
    diff = end_vec - check
    for f in pitzDaily_fields:
        with diff.mmap_data(f) as v:
            assert np.all(np.abs(v()) < 1e-6)
# ~\~ end

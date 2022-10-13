from pathlib import Path
from shutil import copytree

from pylsoFoam.vector import BaseCase
from pylsoFoam.foam import (block_mesh, foam, map_fields)

cylinder_fields = ["p", "U", "phi", "phi_0", "pMean", "pPrime2Mean", "U_0", "UMean", "UPrime2Mean"]

def test_interpolation(tmp_path):
    coarse_path = tmp_path / "coarse"
    fine_path = tmp_path / "fine"
    data = Path(".") / "test" / "cases"
    copytree(data / "c7_coarse", coarse_path)
    copytree(data / "c7_fine", fine_path)

    coarse_base = BaseCase(coarse_path, "baseCase")
    coarse_base.fields = cylinder_fields

    fine_base = BaseCase(fine_path, "baseCase")
    fine_base.fields = cylinder_fields

    block_mesh(coarse_base)
    block_mesh(fine_base)

    coarse_base_vec = coarse_base.new_vector()
    t10_coarse = foam("pimpleFoam", dt=1, x=coarse_base_vec, t_0=0, t_1=10)
    assert t10_coarse.dirname.exists()
    t10_fine = map_fields(t10_coarse, fine_base)
    assert t10_fine.dirname.exists()
    t20_fine = foam("pimpleFoam", dt=0.1, x=t10_fine, t_0=10, t_1=11)
    assert t20_fine.dirname.exists()


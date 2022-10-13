# ~\~ language=Python filename=pylsoFoam/foam.py
# ~\~ begin <<lit/architecture.md|pylsoFoam/foam.py>>[init]
import subprocess
import math
from typing import Optional, Union

from .vector import (BaseCase, Vector, parameter_file, get_times)

# ~\~ begin <<lit/architecture.md|pintfoam-map-fields>>[init]
def map_fields(source: Vector, target: BaseCase, consistent=True, map_method=None) -> Vector:
    """Wrapper for OpenFOAM's mapFields

    Use consistent=False if the initial and final boundaries differ.
    Valid arguments for `map_method`: mapNearest, interpolate, cellPointInterpolate
    """
    result = target.new_vector()
    result.time = source.time
    arg_lst = ["mapFields"]
    if consistent:
        arg_lst.append("-consistent")
    if map_method is not None:
        arg_lst.extend(["-mapMethod", map_method])
    arg_lst.extend(["-sourceTime", source.time, source.path.resolve()])
    subprocess.run(arg_lst, cwd=result.path, check=True)
    (result.path / "0").rename(result.dirname)
    return result
# ~\~ end
# ~\~ begin <<lit/architecture.md|pintfoam-set-fields>>[init]
def set_fields(v, *, default_field_values, regions):
    """Wrapper for OpenFOAM's setFields."""
    x = parameter_file(v, "system/setFieldsDict")
    x['defaultFieldValues'] = default_field_values
    x['regions'] = regions
    x.writeFile()
    subprocess.run("setFields", cwd=v.path, check=True)
# ~\~ end
# ~\~ begin <<lit/architecture.md|pintfoam-block-mesh>>[init]
def block_mesh(case: BaseCase):
    """Wrapper for OpenFOAM's blockMesh."""
    subprocess.run("blockMesh", cwd=case.path, check=True)
# ~\~ end
# ~\~ begin <<lit/architecture.md|pintfoam-epsilon>>[init]
epsilon = 1e-6
# ~\~ end
# ~\~ begin <<lit/architecture.md|pintfoam-solution>>[init]
def foam(solver: str, dt: float, x: Vector, t_0: float, t_1: float,
         write_interval: Optional[float] = None,
         job_name: Optional[str] = None,
         write_control: str = "runTime") -> Vector:
    """Call an OpenFOAM code.

    Args:
        solver: The name of the solver (e.g. "icoFoam", "scalarTransportFoam" etc.)
        dt:     deltaT parameter
        x:      initial state
        t_0:    startTime (should match that in initial state)
        t_1:    endTime
        write_interval: if not given, this is computed so that only the endTime
                is written.

    Returns:
        The `Vector` representing the end state.
    """
    # ~\~ begin <<lit/architecture.md|pintfoam-solution-function>>[init]
    assert abs(float(x.time) - t_0) < epsilon, f"Times should match: {t_0} != {x.time}."
    y = x.clone(job_name)
    write_interval = write_interval or (t_1 - t_0)
    # ~\~ begin <<lit/architecture.md|set-control-dict>>[init]
    backup = open(y.path / "system" / "controlDict", "r").read()
    for i in range(5):   # this sometimes fails, so we try a few times, maybe disk sync issue?
        try:
            print(f"Attempt {i+1} at writing controlDict")
            controlDict = parameter_file(y, "system/controlDict")
            controlDict.content['startFrom'] = "latestTime"
            controlDict.content['startTime'] = float(t_0)
            controlDict.content['endTime'] = float(t_1)
            controlDict.content['deltaT'] = float(dt)
            controlDict.content['writeInterval'] = float(write_interval)
            controlDict.content['writeControl'] = write_control
            controlDict.writeFile()
            break
        except Exception as e:
            exception = e
            open(y.path / "system" / "controlDict", "w").write(backup)
    else:
        raise exception

    # ~\~ end
    # ~\~ begin <<lit/architecture.md|run-solver>>[init]
    with open(y.path / "log.stdout", "w") as logfile, \
         open(y.path / "log.stderr", "w") as errfile:
        subprocess.run(solver, cwd=y.path, check=True, stdout=logfile, stderr=errfile)
    # ~\~ end
    # ~\~ begin <<lit/architecture.md|return-result>>[init]
    t1_str = get_times(y.path)[-1]
    return Vector(y.base, y.case, t1_str)
    # ~\~ end
    # ~\~ end
# ~\~ end
# ~\~ end

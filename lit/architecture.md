# Architecture
From the perspective of the Parareal algorithm we are solving an ODE.


## Implementation
The abstract `Vector`, defined below, represents any single state in the simulation. In OpenFOAM we have the following folder structure:

```
├── 0
│   ├── p
│   └── U
├── 1
│   └── <... data fields ...>
├── <... time directories ...>
├── constant
│   ├── transportProperties
│   └── turbulenceProperties
└── system
    ├── blockMeshDict
    ├── controlDict
    ├── decomposeParDict
    ├── fvSchemes
    └── fvSolution
```

For our application a `Vector` is then a combination of an OpenFOAM case (i.e. the folder structure above), and a string denoting the time directory matching the referred snapshot. The directory structure containing only the `0` time is now the `BaseCase`. We can copy a `Vector` by copying the contents of the `BaseCase` and the single time directory that belongs to that `Vector`.

``` {.python file=pylsoFoam/vector.py}
from __future__ import annotations

import operator
import mmap
import weakref
import gc

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from shutil import copytree, rmtree   # , copy
from typing import List, Optional

from byteparsing import parse_bytes, foam_file

from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile  # type: ignore
from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory      # type: ignore

<<base-case>>
<<pintfoam-vector>>
```

### Base case
We will operate on a `Vector` the same way everything is done in OpenFOAM, that is:

1. Copy-paste a case (known as the base case)
2. Edit the copy with new simulation parameters
3. Run the simulation

This is why for every `Vector` we define a `BaseCase` that is used to generate new vectors. The `BaseCase` should have only one time directory containing the initial conditions, namely `0`. The simulation generates new folders containing the data corresponding to different times. The time is coded, somewhat uncomfortably, in the directory name (`0.01`, `0.02`, and so on), which is why we store the time coordinate as a string.

The class `Vector` takes care of all those details.

``` {.python #base-case}
@dataclass
class BaseCase:
    """Base case is a cleaned version of the system. If it contains any fields,
    it will only be the `0` time. Any field that is copied for manipulation will
    do so on top of an available base case in the `0` slot."""
    root: Path
    case: str
    fields: Optional[List[str]] = None

    @property
    def path(self):
        return self.root / self.case

    def new_vector(self, name: Optional[str] = None):
        """Creates new `Vector` using this base case."""
        new_case = name or uuid4().hex
        new_path = self.root / new_case
        if not new_path.exists():
            copytree(self.path, new_path)
        return Vector(self, new_case, "0")

    def all_vector_paths(self):
        """Iterates all sub-directories in the root."""
        return (x for x in self.root.iterdir()
                if x.is_dir() and x.name != self.case)

    def clean(self):
        """Deletes all vectors of this base-case."""
        for path in self.all_vector_paths():
            rmtree(path)
```

In our implementation, if no name is given to a new vector, a random one is generated.

### Retrieving files and time directories
Note that the `BaseCase` has a property `path`. The same property will be defined in `Vector`. We can use this common property to retrieve a `SolutionDirectory`, `ParameterFile` or `TimeDirectory`.

- [ ] These are PyFoam routines that may need to be replaced

``` {.python #pintfoam-vector}
def solution_directory(case):
    return SolutionDirectory(case.path)

def parameter_file(case, relative_path):
    return ParsedParameterFile(case.path / relative_path)

def time_directory(case):
    return solution_directory(case)[case.time]


def get_times(path):
    """Get all the snapshots in a case, sorted on floating point value."""
    def isfloat(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    return sorted(
        [s.name for s in path.iterdir() if isfloat(s.name)],
        key=float)
```

### Vector
The `Vector` class stores a reference to the `BaseCase`, a case name and a time.

``` {.python #pintfoam-vector}
@dataclass
class Vector:
    base: BaseCase
    case: str
    time: str

    <<pintfoam-vector-properties>>
    <<pintfoam-vector-clone>>
    <<pintfoam-vector-operate>>
    <<pintfoam-vector-operators>>
```

From a vector we can extract a file path pointing to the specified time slot, list the containing files and read out `internalField` from any of those files.

``` {.python #pintfoam-vector-properties}
@property
def path(self):
    """Case path, i.e. the path containing `system`, `constant` and snapshots."""
    return self.base.root / self.case

@property
def fields(self):
    """All fields relevant to this base case."""
    return self.base.fields

@property
def dirname(self):
    """The path of this snapshot."""
    return self.path / self.time

def all_times(self):
    """Get all available times, in order."""
    return [Vector(self.base, self.case, t)
            for t in get_times(self.path)]
```

 We do arithmetic on `Vector` by cloning an existing `Vector` and then modify the `internalField` values inside. This can be done very efficiently using memory-mapped array access. The `mmap_data` member takes care of loading the data and closing the file when we're done with it in a nifty context manager.

``` {.python #pintfoam-vector-properties}
@contextmanager
def mmap_data(self, field):
    """Context manager that yields a **mutable** reference to the data contained
    in this snapshot. Mutations done to this array are mmapped to the disk directly."""
    f = (self.dirname / field).open(mode="r+b")
    with mmap.mmap(f.fileno(), 0) as mm:
        content = parse_bytes(foam_file, mm)
        try:
            result = content["data"]["internalField"]
        except KeyError as e:
            print(content)
            raise e
        yield weakref.ref(result)
        del result
        del content
        gc.collect()
```

We clone a vector by creating a new vector and copying the internal fields.

``` {.python #pintfoam-vector-clone}
def clone(self, name: Optional[str] = None) -> Vector:
    """Clone this vector to a new one. The clone only contains this single snapshot."""
    x = self.base.new_vector(name)
    x.time = self.time
    rmtree(x.dirname, ignore_errors=True)
    copytree(self.dirname, x.dirname)
    return x
```

In order to apply the parareal algorithm to our vectors (or indeed, any other algorithm worth that name), we need to define how to operate with them. Particularly, we'll need to implement:

- Vector addition and subtraction (as we'll need to sum and subtract the results of applying the coarse and fine integrators)
- Vector scaling (as the integrators involve scaling with the inverse of the step)

In order to achieve this, first we'll write generic recipes for **any** operation between vectors and **any** operation between a scalar and a vector:

``` {.python #pintfoam-vector-operate}
def zip_with(self, other: Vector, op) -> Vector:
    x = self.clone()

    for f in self.fields:
        with x.mmap_data(f) as a, other.mmap_data(f) as b:
            a()[:] = op(a(), b())
    return x

def map(self, f) -> Vector:
    x = self.clone()

    for f in self.fields:
        with x.mmap_data(f) as a:
            a()[:] = f(a())
    return x
```

We now have the tools to define vector addition, subtraction and scaling.

``` {.python #pintfoam-vector-operators}
def __sub__(self, other: Vector) -> Vector:
    return self.zip_with(other, operator.sub)

def __add__(self, other: Vector) -> Vector:
    return self.zip_with(other, operator.add)

def __mul__(self, scale: float) -> Vector:
    return self.map(lambda x: x * scale)
```

In the code chunk above we used the so-called magic methods. If we use a minus sign to subtract two vectors, the method `__sub__` is being executed under the hood.

# OpenFOAM calls

``` {.python file=pylsoFoam/foam.py}
import subprocess
import math
from typing import Optional, Union

from .vector import (BaseCase, Vector, parameter_file, get_times)

<<pintfoam-map-fields>>
<<pintfoam-set-fields>>
<<pintfoam-block-mesh>>
<<pintfoam-epsilon>>
<<pintfoam-solution>>
```

## `setFields` utility
We may want to call `setFields` on our `Vector` to setup some test cases.

``` {.python #pintfoam-set-fields}
def set_fields(v, *, default_field_values, regions):
    """Wrapper for OpenFOAM's setFields."""
    x = parameter_file(v, "system/setFieldsDict")
    x['defaultFieldValues'] = default_field_values
    x['regions'] = regions
    x.writeFile()
    subprocess.run("setFields", cwd=v.path, check=True)
```

## `mapFields`
The `mapFields` utility interpolates a field from one mesh onto another. The resulting field values are written to the `0` time directory, so we need to rename that directory after calling `mapFields` for consistency with the `Vector` infrastrucutre.

``` {.python #pintfoam-map-fields}
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
```

## `blockMesh`
The `blockMesh` utility generates an OpenFOAM mesh from a description in the `blockMesh` format. This is usually called on a `baseCase` so that the mesh information is shared by all vectors.

``` {.python #pintfoam-block-mesh}
def block_mesh(case: BaseCase):
    """Wrapper for OpenFOAM's blockMesh."""
    subprocess.run("blockMesh", cwd=case.path, check=True)
```

## Implementation of `Solution`
Remember, the definition of a `Solution`,

``` {.python}
Solution = Callable[[Vector, float, float], Vector]
```

meaning, we write a function taking a current state `Vector`, the time *now*, and the *target* time, returning a new `Vector` for the target time.

The solver will write directories with floating-point valued names. This is a very bad idea by the folks at OpenFOAM, but it is one we'll have to live with. Suppose you have a time-step of $0.1$, what will be the names of the directories if you integrate from $0$ to $0.5$?

``` {.python session=0}
[x * 0.1 for x in range(6)]
```

In Python 3.7, this gives `[0.0, 0.1, 0.2, 0.30000000000000004, 0.4, 0.5]`. Surely, if you give a time-step of $0.1$ to OpenFOAM, it will create a directory named `0.3` instead. We'll define the constant `epsilon` to aid us in identifying the correct state directory given a floating-point time.

``` {.python #pintfoam-epsilon}
epsilon = 1e-6
```

Our solution depends on the solver chosen and the given time-step:

``` {.python #pintfoam-solution}
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
    <<pintfoam-solution-function>>
```

The solver clones a new vector, sets the `controlDict`, runs the solver and then creates a new vector representing the last time slice.

``` {.python #pintfoam-solution-function}
assert abs(float(x.time) - t_0) < epsilon, f"Times should match: {t_0} != {x.time}."
y = x.clone(job_name)
write_interval = write_interval or (t_1 - t_0)
<<set-control-dict>>
<<run-solver>>
<<return-result>>
```

### `controlDict`
Because writing the `controlDict` sometimes fails, we try it a few times. For this we need to create a backup of the original contents of `controlDict`.

``` {.python #set-control-dict}
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

```

### Run solver

``` {.python #run-solver}
with open(y.path / "log.stdout", "w") as logfile, \
     open(y.path / "log.stderr", "w") as errfile:
    subprocess.run(solver, cwd=y.path, check=True, stdout=logfile, stderr=errfile)
```

### Return result
We retrieve the time of the result by looking at the last time directory.

``` {.python #return-result}
t1_str = get_times(y.path)[-1]
return Vector(y.base, y.case, t1_str)
```

# Appendix A: Utils

``` {.python file=pylsoFoam/utils.py}
<<push-dir>>
<<job-names>>
```

## Cleaning up

``` {.python file=pylsoFoam/clean.py}
import argh  # type:ignore
from pathlib import Path
from .vector import BaseCase


@argh.arg("target", help="target path to clean")
@argh.arg("--base_case", help="name of the base-case")
def main(target: Path, base_case: str = "baseCase"):
    """Auxiliary function that deletes all vectors of this base-case."""
    BaseCase(Path(target), base_case).clean()


if __name__ == "__main__":
    argh.dispatch_command(main)
```

## `pushd`

I haven't been able (with simple attempts) to run a case outside the definition directory. Similar to the `pushd` bash command, I define a little utility in Python:

``` {.python #push-dir}
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Union
import functools
from math import (floor, log10)


def decorator(f):
    """Creates a parametric decorator from a function. The resulting decorator
    will optionally take keyword arguments."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if args and len(args) == 1:
            return f(*args, **kwargs)

        if args:
            raise TypeError(
                "This decorator only accepts extra keyword arguments.")

        return lambda g: f(g, **kwargs)

    return decorated_function


@contextmanager
def pushd(path: Union[str, Path]):
    """Context manager to change directory to given path,
    and get back to current dir at exit."""
    prev = Path.cwd()
    os.chdir(path)

    try:
        yield
    finally:
        os.chdir(prev)
```

## Job names

``` {.python #job-names}
def generate_job_name(n, t_0, t_1, uid, id, tlength=4):
    """ Auxiliary function to generate a job name."""

    def integrify(t, length=tlength):
        """ Auxiliary function for converting a float into an integer. """
        if t==0:
            return 0
        else:
            aux = t * 10 ** -floor(log10(t)) # Remove trailing zeros
            aux = aux * 10 ** (length - 1) # Displace the decimal point to the right
        return int(aux)

    def trim_zeros(t):
        """Trim zeros

        for instance:

        trim_zeros(0.0012345)
        1.2345
        """
        if t == 0:
            return 0
        else:
            return t * 10 ** -floor(log10(t))

    def stringify(t, length=tlength):
        """ Turn a float into a string with a given length

        for instance:

        stringify(0.0012345, length=2)
        '12'
        """
        format_string = "." + str(length-1) + "f" # For instance: .5f
        return f"{trim_zeros(t):{format_string}}".replace(".", "")

    return f"{n}-{stringify(t_0)}-{stringify(t_1)}-{id}-{uid.hex}"
```

#!/bin/bash

foamCleanTutorials
blockMesh | tee log.blockMesh
checkMesh | tee log.checkMesh
renumberMesh -overwrite -noFunctionObjects | tee log.renumbermesh
pimpleFoam | tee log.pimplefoam
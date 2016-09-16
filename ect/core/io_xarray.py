# The MIT License (MIT)
# Copyright (c) 2016 by the ECT Development Team and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Description
===========

.. warning:: This module is only partially implemented and lacks essential functionality.

This module implements the `xarray`_ and netCDF `Common Data Model`_ data access for the CCI Toolbox.

.. _xarray: http://xarray.pydata.org/en/stable/
.. _Common Data Model: http://www.unidata.ucar.edu/software/thredds/current/netcdf-java/CDM

Components
==========
"""
from datetime import datetime
from glob import glob
from typing import Sequence

import pandas as pd
import xarray as xr


def open_xarray_dataset(paths, preprocess=True, chunks=None, **kwargs) -> xr.Dataset:
    """
    Adapted version of the xarray 'open_mfdataset' function.
    """
    if isinstance(paths, str):
        paths = sorted(glob(paths))
    if not paths:
        raise IOError('no files to open')

    if not preprocess:
        return xr.open_mfdataset(paths, concat_dim='time')

    # open all datasets
    lock = xr.backends.api._default_lock(paths[0], None)
    # TODO (forman, 20160601): align with chunking from netcdf metadata attribute

    datasets = []
    engine = 'netcdf4'
    for p in paths:
        datasets.append(xr.open_dataset(p, engine=engine, decode_cf=False, chunks=chunks or {}, lock=lock, **kwargs))

    preprocessed_datasets = []
    file_objs = []
    for ds in datasets:
        pds = _preprocess_datasets(ds)
        if pds is None:
            ds._file_obj.close()
        else:
            pds_decoded = xr.decode_cf(pds)
            preprocessed_datasets.append(pds_decoded)
            file_objs.append(ds._file_obj)

    combined_datasets = _combine_datasets(preprocessed_datasets)
    combined_datasets._file_obj = xr.backends.api._MultiFileCloser(file_objs)
    return combined_datasets


def _combine_datasets(datasets: Sequence[xr.Dataset]) -> xr.Dataset:
    """
    Combines all datasets into a single.
    """
    if len(datasets) == 0:
        raise ValueError('No dataset for combining')
    if 'time' in datasets[0].dims:
        return xr.auto_combine(datasets, concat_dim='time')
    else:
        time_index = [_extract_time_index(ds) for ds in datasets]
        return xr.concat(datasets, pd.Index(time_index, name='time'))


def _preprocess_datasets(dataset: xr.Dataset) -> xr.Dataset:
    """
    Modifies datasets, so that it is netcdf-CF compliant
    """
    for var in dataset.data_vars:
        attrs = dataset[var].attrs
        if '_FillValue' in attrs and 'missing_value' in attrs:
            # xarray as of version 0.7.2 does not handle it correctly,
            # if both values are set to NaN. (because the values are compared using '==')
            # reproducible with  engine='netcdf4'
            # https://github.com/pydata/xarray/issues/997
            del attrs['missing_value']
    return dataset


def _extract_time_index(ds: xr.Dataset) -> datetime:
    time_coverage_start = ds.attrs['time_coverage_start']
    time_coverage_end = ds.attrs['time_coverage_end']
    try:
        # print(time_coverage_start, time_coverage_end)
        time_start = datetime.strptime(time_coverage_start, "%Y%m%dT%H%M%SZ")
        time_end = datetime.strptime(time_coverage_end, "%Y%m%dT%H%M%SZ")
        return time_end
    except ValueError:
        return None

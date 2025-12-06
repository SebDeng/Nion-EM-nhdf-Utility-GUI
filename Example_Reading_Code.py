"""
This script reads a data and metadata file and prints out the data and metadata.
Usage:
 python read_nhdf.py /path/to/data_and_metadata.nhdf
required packages, either:
 pip install numpy h5py niondata
 conda install -c conda-forge numpy h5py niondata
"""

import argparse
import h5py
import json
import numpy.typing
import pathlib
import pprint
import typing

from nion.data import Calibration
from nion.data import DataAndMetadata
from nion.utils import Converter

_NDArray = numpy.typing.NDArray[typing.Any]

def read_data_and_metadata(path: pathlib.Path) -> DataAndMetadata.DataAndMetadata:
    # open the h5py file (aka nhdf)
    with h5py.File(str(path), "r") as f:
        # read the data group
        dg = f["data"]
        # get the first key in the group. in the future there may be multiple data items per file.
        key0 = list(sorted(dg.keys()))[0]
        # get the dataset
        ds = dg[key0]
        # read the properties attribute
        json_properties = json.loads(ds.attrs["properties"])
        # cast the dataset to an NDArray
        data = typing.cast(_NDArray, ds)
        # create a DataDescriptor from the properties. describes the meaning of the data dimensions.
        data_descriptor = DataAndMetadata.DataDescriptor(
            is_sequence=json_properties.get("is_sequence", False),
            collection_dimension_count=json_properties.get("collection_dimension_count", 0),
            datum_dimension_count=json_properties.get("datum_dimension_count", 0)
        )
        # create a DataMetadata from the properties. describes the data and metadata.
        data_metadata = DataAndMetadata.DataMetadata(
            data_shape_and_dtype=(data.shape, data.dtype),
            intensity_calibration=Calibration.Calibration.from_rpc_dict(json_properties.get("intensity_calibration", {})),
            dimensional_calibrations=[typing.cast(Calibration.Calibration, Calibration.Calibration.from_rpc_dict(d)) for d in json_properties.get("dimensional_calibrations", [])],
            metadata=json_properties.get("metadata", {}),
            timestamp=Converter.DatetimeToStringConverter().convert_back(json_properties.get("created", "")),
            data_descriptor=data_descriptor,
            timezone=json_properties.get("timezone", None),
            timezone_offset=json_properties.get("timezone_offset", None)
        )
        # return a DataAndMetadata object
        return DataAndMetadata.DataAndMetadata(
            data,
            data_shape_and_dtype=data_metadata.data_shape_and_dtype,
            intensity_calibration=data_metadata.intensity_calibration,
            dimensional_calibrations=data_metadata.dimensional_calibrations,
            metadata=data_metadata.metadata,
            timestamp=data_metadata.timestamp,
            data_descriptor=data_metadata.data_descriptor,
            timezone=data_metadata.timezone,
            timezone_offset=data_metadata.timezone_offset
        )

argparser = argparse.ArgumentParser()

argparser.add_argument("path", type=pathlib.Path, help="Path to data and metadata file")

args = argparser.parse_args()

d = read_data_and_metadata(pathlib.Path(args.path))

# print out the data and metadata information (not the data itself; that would be too big)
print(f"{d.data.shape=}")
print(f"{d.data_descriptor=}")
print(f"{d.data_descriptor.is_sequence=} {d.data_descriptor.collection_dimension_count=} {d.data_descriptor.datum_dimension_count=}")
print(f"{d.intensity_calibration=}")
print(f"{d.dimensional_calibrations=}")
print(f"{d.timestamp=}")
print(f"{d.timezone=}")
print(f"{d.timezone_offset=}")
print("metadata:")
print(pprint.pformat(d.metadata))

#Author: Chris Meyer @ nion-software; https://gist.github.com/cmeyer
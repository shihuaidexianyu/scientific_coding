"""Small fully described CSV fixtures for integrity tests."""


def contract_text(name="TestDataset", payload="data.csv"):
    return f'''# Dataset used by the isolated test.
name = "{name}"

# Scientific interface version.
version = 1

# One scalar measurement per identified test observation.
description = "Small CSV measurement table for integrity tests."

# Serialized payload semantics.
[data]

# Relative payload location.
path = "{payload}"

# UTF-8 CSV with a header.
format = "csv"

# Observed numeric values, with field names in the CSV header.
representation = "scalar_measurements"

# One row per observation and columns as declared by the header.
dimensions = ["observation", "field"]

# Text identifiers and numerical values.
dtype = "mixed_record"

# Dimensionless toy measurements.
unit = "dimensionless"

# Empty values are not allowed in declared fields.
missing_value = "not_allowed"

# Observation semantics.
[sample]

# Independent synthetic measurement.
identity = "observation"

# Retain written row order.
ordering = "file_order"

# Toy population only.
population = "synthetic test observations"

# Reader instructions for this table.
[reading]

# Concrete standard-library read method.
example = "list(csv.DictReader(open('{payload}', newline='', encoding='utf-8')))"

# CSV values arrive as strings; consumers interpret the declared columns.
in_memory = "list of row dictionaries with header-named fields"
'''

#!/usr/bin/env python3
"""Validate YAML configuration files against JSON schema."""
import json
import sys
from datetime import date, datetime

import yaml
from jsonschema import ValidationError, validate


def convert_dates_to_strings(obj):
    """Recursively convert date objects to ISO format strings."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_dates_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates_to_strings(item) for item in obj]
    else:
        return obj


def convert_keys_to_strings(obj):
    """Recursively convert all dictionary keys to strings."""
    if isinstance(obj, dict):
        return {str(k): convert_keys_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_keys_to_strings(item) for item in obj]
    else:
        return obj


def validate_yaml_schema(yaml_file, schema_file):
    try:
        # Load YAML file
        with open(yaml_file, encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Convert date objects to strings
        data = convert_dates_to_strings(data)

        # Convert all keys to strings to avoid regex issues
        data = convert_keys_to_strings(data)

        # Load JSON schema
        with open(schema_file, encoding='utf-8') as f:
            schema = json.load(f)

        # Validate against schema
        validate(instance=data, schema=schema)
        # print(f"✅ {yaml_file} passed schema validation")
        return True

    except ValidationError as e:
        print(f"❌ Schema validation failed: {e.message}")
        print(
            f"   Failed at path: {' -> '.join(str(x) for x in e.absolute_path)}",
        )

        # Show the actual vs expected value
        if hasattr(e, 'instance'):
            print(
                f"   Found value: {repr(e.instance)} (type: {type(e.instance).__name__})",
            )
        if hasattr(e, 'schema') and 'type' in e.schema:
            print(f"   Expected type: {e.schema['type']}")

        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Error type: {type(e).__name__}")

        # Add debugging information
        if 'expected string or bytes-like object' in str(e):
            print(
                '   This error suggests your YAML has numeric keys that conflict with JSON schema patternProperties.',
            )
            print(
                '   Consider checking your YAML file for numeric keys or updating your JSON schema.',
            )

        return False


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python validate_config.py <yaml_file> <schema_file>')
        sys.exit(1)

    success = validate_yaml_schema(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)

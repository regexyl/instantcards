#!/usr/bin/env python3
"""
Environment variable loader that transforms Terraform variable names.

This script loads environment variables from a .env file and transforms
variables that start with "TF_VAR_" by removing the prefix and capitalizing
the rest of the name. It then prints export statements to be sourced by the shell.
"""

import os
import sys
from pathlib import Path
from typing import Dict


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}

    if not env_path.exists():
        print(f"Warning: .env file not found at {env_path}", file=sys.stderr)
        return env_vars

    with open(env_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse key=value pairs
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                env_vars[key] = value
            else:
                print(
                    f"Warning: Invalid line {line_num} in {env_path}: {line}", file=sys.stderr)

    return env_vars


def transform_tf_vars(env_vars: Dict[str, str]) -> Dict[str, str]:
    """Transform TF_VAR_ prefixed variables by removing prefix and capitalizing."""
    transformed = {}

    for key, value in env_vars.items():
        if key.startswith('TF_VAR_'):
            # Remove TF_VAR_ prefix and capitalize the rest
            new_key = key[7:].upper()
            transformed[new_key] = value
        else:
            transformed[key] = value

    return transformed


def export_to_shell(env_vars: Dict[str, str]) -> None:
    """Export environment variables to shell by printing export statements."""
    for key, value in env_vars.items():
        # Escape special characters in the value
        escaped_value = value.replace('"', '\\"').replace('$', '\\$')
        print(f'export {key}="{escaped_value}"')


def print_env_vars(env_vars: Dict[str, str]) -> None:
    """Print all environment variables for debugging."""
    print("\nEnvironment variables loaded:", file=sys.stderr)
    for key, value in env_vars.items():
        print(f"  {key}={value}", file=sys.stderr)
    print(file=sys.stderr)


def main():
    """Main function to load and transform environment variables."""
    # Look for .env file in current directory or project root
    current_dir = Path.cwd()
    project_root = current_dir.parent if current_dir.name == 'scripts' else current_dir

    env_paths = [
        current_dir / '.env',
        project_root / '.env',
        project_root / 'terraform' / '.env'
    ]

    env_path = None
    for path in env_paths:
        if path.exists():
            env_path = path
            break

    if not env_path:
        print("Error: No .env file found in current directory, project root, or terraform directory", file=sys.stderr)
        sys.exit(1)

    print(f"Loading environment variables from: {env_path}", file=sys.stderr)

    env_vars = load_env_file(env_path)
    transformed_vars = transform_tf_vars(env_vars)

    print_env_vars(transformed_vars)
    export_to_shell(transformed_vars)

    print(
        f"Loaded {len(transformed_vars)} environment variables ✅", file=sys.stderr)


if __name__ == '__main__':
    main()

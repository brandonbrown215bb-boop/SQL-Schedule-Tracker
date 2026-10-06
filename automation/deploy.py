"""Deployment Automation Script.

Builds the PyInstaller executable, generates version.txt,
and deploys all required files to the shared network drive.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import yaml


def validate_version(version: str) -> bool:
    """Validate version string format (semantic versioning)."""
    return bool(re.match(r"^\d+\.\d+\.\d+$", version.strip()))


def prepare_production_config(template_config_path: str, dest_config_path: str, deploy_dir: str) -> None:
    """Read local dev template config.yaml and write production config.yaml to deployment folder with P: drive paths."""
    with open(template_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config["sqlite_path"] = r"P:\Detailing Schedule 2019\schedule.db"
    config["excel_path"] = r"P:\Detailing Schedule 2019\SCHDetailingReport_all_plants_MASTER.xlsm"
    config["unedited_reports_dir"] = r"P:\Detailing Schedule 2019\Unedited Reports"
    config["update_source_dir"] = deploy_dir

    with open(dest_config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=True)


def main():
    print("=== SQL Schedule Tracker Deployment Automation ===")

    # 1. Ask for version number
    version = ""
    while not validate_version(version):
        version_input = input("Enter new version number (e.g. 1.0.1): ").strip()
        if validate_version(version_input):
            version = version_input
        else:
            print("Invalid format. Please enter a valid semantic version (X.Y.Z).")

    # 2. Load config.yaml to get default update_source_dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    config_path = os.path.join(project_root, "config.yaml")

    default_dest = ""
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                default_dest = config.get("update_source_dir", "")
        except Exception as e:
            print(f"Warning: Could not read default update_source_dir from config.yaml: {e}")

    # 3. Ask for deployment directory
    print(f"\nDefault deployment folder: {default_dest}")
    dest_input = input("Enter target network deployment folder [Press Enter for default]: ").strip()
    dest_dir = dest_input if dest_input else default_dest

    if not dest_dir:
        print("Error: No deployment folder specified. Aborting.")
        sys.exit(1)

    # Convert to absolute path
    dest_dir = os.path.abspath(dest_dir)
    print(f"Deploying to: {dest_dir}\n")

    # Ask for confirmation
    confirm = input(f"Confirm build and deploy version v{version} to '{dest_dir}'? (y/n): ").strip().lower()
    if confirm != "y":
        print("Deployment cancelled.")
        sys.exit(0)

    # 4. Build application using build.bat
    build_bat_path = os.path.join(project_root, "build.bat")
    if not os.path.exists(build_bat_path):
        print(f"Error: build.bat not found at {build_bat_path}")
        sys.exit(1)

    print("\nRunning PyInstaller build...")
    try:
        # Run PyInstaller build from the project root
        result = subprocess.run([build_bat_path], cwd=project_root, check=True, shell=True)
        if result.returncode != 0:
            print("Error: PyInstaller build failed. Aborting deployment.")
            sys.exit(1)
        print("PyInstaller build completed successfully.")
    except Exception as e:
        print(f"Error: Build subprocess failed: {e}")
        sys.exit(1)

    # 5. Write local version.txt
    local_version_path = os.path.join(project_root, "version.txt")
    print(f"\nWriting local version file to {local_version_path}...")
    try:
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(version + "\n")
    except Exception as e:
        print(f"Error: Failed to write local version.txt: {e}")
        sys.exit(1)

    # 6. Copy files to deployment folder
    dist_exe = os.path.join(project_root, "dist", "Detailing Schedule.exe")
    template_config = os.path.join(project_root, "config.yaml")

    if not os.path.exists(dist_exe):
        print(f"Error: Built executable not found at {dist_exe}")
        sys.exit(1)

    # Create destination directory if it doesn't exist
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: Failed to create target folder {dest_dir}: {e}")
        sys.exit(1)

    # Target file paths
    dest_exe = os.path.join(dest_dir, "Detailing Schedule.exe")
    dest_config = os.path.join(dest_dir, "config.yaml")
    dest_version = os.path.join(dest_dir, "version.txt")

    print("\nCopying files to network share...")
    try:
        # Copy executable
        print(f"Copying '{dist_exe}' -> '{dest_exe}'")
        shutil.copy2(dist_exe, dest_exe)

        # Generate production config.yaml template with P: drive paths
        print(f"Writing production template config -> '{dest_config}'")
        prepare_production_config(template_config, dest_config, dest_dir)

        # Copy version.txt
        print(f"Copying '{local_version_path}' -> '{dest_version}'")
        shutil.copy2(local_version_path, dest_version)

        # Copy installer script if present
        installer_src = os.path.join(script_dir, "Install Detailing Schedule.bat")
        if os.path.exists(installer_src):
            dest_installer = os.path.join(dest_dir, "Install Detailing Schedule.bat")
            print(f"Copying '{installer_src}' -> '{dest_installer}'")
            shutil.copy2(installer_src, dest_installer)

        print("\n=== Deployment SUCCESSFUL! ===")
        print(f"Version v{version} is now available for users on the shared network drive.")
    except Exception as e:
        print(f"\nError: File copy failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

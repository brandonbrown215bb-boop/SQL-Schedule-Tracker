"""Auto-Bump and Deploy Automation Script.

Automatically bumps the patch version, runs PyInstaller build, and deploys the
executable, config template, and version.txt to the network update share.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import yaml


def parse_version(v_str: str) -> list[int] | None:
    """Parse version string format (semantic versioning X.Y.Z)."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", v_str.strip())
    if not match:
        return None
    return [int(match.group(1)), int(match.group(2)), int(match.group(3))]


def format_version(v_parts: list[int]) -> str:
    """Format version parts list back to a string."""
    return f"{v_parts[0]}.{v_parts[1]}.{v_parts[2]}"


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
    print("============================================================")
    print("        SQL Schedule Tracker Auto-Bump & Deploy")
    print("============================================================")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # 1. Determine local version from version.txt
    local_version_path = os.path.join(project_root, "version.txt")
    local_version_str = "0.0.0"
    if os.path.exists(local_version_path):
        try:
            with open(local_version_path, encoding="utf-8") as f:
                local_version_str = f.readline().strip()
        except Exception as e:
            print(f"Warning: Failed to read local version.txt: {e}")

    local_version = parse_version(local_version_str) or [0, 0, 0]
    print(f"Current local version: {format_version(local_version)}")

    # 2. Determine target deployment path from config.yaml
    config_path = os.path.join(project_root, "config.yaml")
    deploy_dir = "P:\\Detailing Schedule 2019\\Schedule App"
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                deploy_dir = config.get("update_source_dir", deploy_dir)
        except Exception as e:
            print(f"Warning: Could not read update_source_dir from config.yaml: {e}")

    print(f"Deployment folder target: {deploy_dir}")

    # 3. Read remote version if available
    remote_version_path = os.path.join(deploy_dir, "version.txt")
    remote_version = None
    if os.path.exists(remote_version_path):
        try:
            with open(remote_version_path, encoding="utf-8") as f:
                remote_version_str = f.readline().strip()
                remote_version = parse_version(remote_version_str)
                if remote_version:
                    print(f"Current remote version on P: drive: {format_version(remote_version)}")
        except Exception as e:
            print(f"Warning: Could not read remote version.txt (P: drive might be offline): {e}")

    # Determine base version to bump (use the newer of local vs remote)
    base_version = local_version
    if remote_version and remote_version > local_version:
        print(f"Note: Remote version ({format_version(remote_version)}) is newer than local version ({format_version(local_version)}).")
        base_version = remote_version

    # 4. Calculate bumped version (increment patch version by default)
    bumped_version = list(base_version)
    bumped_version[2] += 1
    bumped_version_str = format_version(bumped_version)

    # 5. Prompt user for version override or confirmation
    try:
        user_input = input(f"Enter version to deploy [Press Enter for bumped v{bumped_version_str}]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nDeployment cancelled.")
        sys.exit(0)

    if user_input:
        target_version = parse_version(user_input)
        if not target_version:
            print(f"Error: Invalid version format '{user_input}'. Must be X.Y.Z")
            sys.exit(1)
        final_version_str = format_version(target_version)
    else:
        final_version_str = bumped_version_str

    print(f"Target deployment version: {final_version_str}")

    # 6. Pre-flight checks on deployment directory
    # Verify that we can write to the network folder before spending time building
    print("\nPerforming pre-flight directory check...")
    if not os.path.exists(deploy_dir):
        print(f"Attempting to create deployment folder: {deploy_dir}")
        try:
            os.makedirs(deploy_dir, exist_ok=True)
        except Exception as e:
            print(f"Error: Target deployment directory could not be created/accessed: {e}")
            print("Please make sure the P: drive is connected and you have write permissions.")
            sys.exit(1)

    test_write_path = os.path.join(deploy_dir, ".write_test")
    try:
        with open(test_write_path, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_write_path)
        print("Pre-flight directory check passed. Folder is writable.")
    except Exception as e:
        print(f"Error: Target deployment directory is not writable: {e}")
        print("Please make sure the P: drive is connected and you have write permissions.")
        sys.exit(1)

    # 7. Ask for final confirmation
    try:
        confirm = input(f"Confirm build & deploy of v{final_version_str} to '{deploy_dir}'? (y/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nDeployment cancelled.")
        sys.exit(0)

    if confirm != "y":
        print("Deployment cancelled.")
        sys.exit(0)

    # 8. Update local version.txt temporarily
    # We back up the original to restore if build/deploy fails
    old_local_version_content = local_version_str
    try:
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(final_version_str + "\n")
    except Exception as e:
        print(f"Error: Failed to write version.txt locally: {e}")
        sys.exit(1)

    # 9. Run PyInstaller build
    build_bat_path = os.path.join(project_root, "build.bat")
    if not os.path.exists(build_bat_path):
        print(f"Error: build.bat not found at {build_bat_path}")
        # Restore version.txt
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(old_local_version_content + "\n")
        sys.exit(1)

    print("\nRunning PyInstaller build (build.bat)...")
    try:
        result = subprocess.run([build_bat_path], cwd=project_root, check=True, shell=True)
        if result.returncode != 0:
            print("Error: PyInstaller build failed.")
            # Restore version.txt
            with open(local_version_path, "w", encoding="utf-8") as f:
                f.write(old_local_version_content + "\n")
            sys.exit(1)
        print("PyInstaller build completed successfully.")
    except Exception as e:
        print(f"Error running build subprocess: {e}")
        # Restore version.txt
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(old_local_version_content + "\n")
        sys.exit(1)

    # 10. Copy files to deployment folder
    dist_exe = os.path.join(project_root, "dist", "Detailing Schedule.exe")
    template_config = os.path.join(project_root, "config.yaml")

    if not os.path.exists(dist_exe):
        print(f"Error: Built executable not found at {dist_exe}")
        # Restore version.txt
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(old_local_version_content + "\n")
        sys.exit(1)

    dest_exe = os.path.join(deploy_dir, "Detailing Schedule.exe")
    dest_config = os.path.join(deploy_dir, "config.yaml")
    dest_version = os.path.join(deploy_dir, "version.txt")

    print("\nCopying files to network share...")
    try:
        # Copy executable
        print(f"Copying '{dist_exe}' -> '{dest_exe}'")
        shutil.copy2(dist_exe, dest_exe)

        # Generate production config.yaml template with P: drive paths
        print(f"Writing production template config -> '{dest_config}'")
        prepare_production_config(template_config, dest_config, deploy_dir)

        # Copy version.txt
        print(f"Copying '{local_version_path}' -> '{dest_version}'")
        shutil.copy2(local_version_path, dest_version)

        # Copy installer script if present
        installer_src = os.path.join(script_dir, "Install Detailing Schedule.bat")
        if os.path.exists(installer_src):
            dest_installer = os.path.join(deploy_dir, "Install Detailing Schedule.bat")
            print(f"Copying '{installer_src}' -> '{dest_installer}'")
            shutil.copy2(installer_src, dest_installer)

        print("\n============================================================")
        print("                 DEPLOYMENT SUCCESSFUL!")
        print("============================================================")
        print(f"Version v{final_version_str} is now live at: {deploy_dir}")
        print("Client apps will automatically detect and apply the update on start.")
    except Exception as e:
        print(f"\nError: File copy failed: {e}")
        print("Please check connection to the P: drive.")
        # Restore version.txt
        with open(local_version_path, "w", encoding="utf-8") as f:
            f.write(old_local_version_content + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

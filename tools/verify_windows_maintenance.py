"""Exercise real Inno upgrade/repair prompts using an isolated test identity.

The small fixtures compile the production installer script unchanged. They carry
a marker payload, never replace an owner's installation, and never launch SAM.
"""

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

from release_metadata import project_version

ROOT = Path(__file__).resolve().parents[1]


def hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def decline_prompt(installer, log, application, expected):
    """Read/cancel only a dialog containing this test's unique application name."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetDlgItem.restype = wintypes.HWND
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    process = subprocess.Popen([str(installer), "/SP-", "/NORESTART", f"/LOG={log}"],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    found = []

    @callback_type
    def window(handle, _parameter):
        if not user.IsWindowVisible(handle):
            return True
        parts = []

        @callback_type
        def child(control, _parameter):
            buffer = ctypes.create_unicode_buffer(4096)
            user.GetWindowTextW(control, buffer, len(buffer))
            parts.append(buffer.value)
            return True
        user.EnumChildWindows(handle, child, 0)
        text = "\n".join(parts)
        if application in text and expected.lower() in text.lower():
            button = user.GetDlgItem(handle, 7)  # IDNO, not an unrelated app's button.
            if button:
                found.append(text)
                user.SendMessageW(button, 0xF5, 0, 0)  # BM_CLICK
                return False
        return True

    try:
        deadline = time.monotonic() + 30
        while not found and process.poll() is None and time.monotonic() < deadline:
            user.EnumWindows(window, 0)
            time.sleep(.05)
        assert found, f"Expected {expected} confirmation was not shown"
        assert process.wait(timeout=30) != 0, "Declining must cancel installation"
        return found[0]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inno", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--previous-version", default="0.7.0.dev6")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows and the Inno compiler are required")
    import winreg

    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    install = work / "custom installed application"
    if install.exists():
        raise ValueError("Use a fresh maintenance-test workdir")
    identity = str(uuid.uuid4()).upper()
    application = f"PNC maintenance test {identity[:8]}"
    key = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{" + identity + "}_is1"
    current = project_version(ROOT, allow_preview=True)
    runtime, fixtures = work / "payload", work / "fixtures"
    runtime.mkdir()
    fixtures.mkdir()
    for index, version in enumerate((args.previous_version, current)):
        (runtime / "pnc-maintenance-test.txt").write_text(version)
        compiled = subprocess.run([str(args.inno.resolve()), "/Q", f"/DAppVersion={version}",
                        "/DWindowsVersion=0.7.0.0", f"/DAppName={application}",
                        "/DAppIdentity={{" + identity + "}", f"/DRuntimeDir={runtime}",
                        f"/DOutputDir={fixtures}", f"/DFileBaseName=fixture-{index}",
                        str(ROOT / "installer/windows/pnc-counter.iss")],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (work / f"compile-{index}.log").write_bytes(compiled.stdout)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout.decode(errors="replace"))
    previous, updated = fixtures / "fixture-0.exe", fixtures / "fixture-1.exe"
    record = {"passed": False, "test_identity": identity, "current": current,
              "previous": args.previous_version, "fixture": "production script with marker payload"}
    userdata = work / "user-data"
    userdata.mkdir()
    for name in ("preferences.json", "model.pt", "results.csv"):
        (userdata / name).write_text("owner data to preserve")
    protected = hashes(userdata)

    def installed_version():
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
            return winreg.QueryValueEx(handle, "DisplayVersion")[0]

    def set_version(version):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as handle:
            winreg.SetValueEx(handle, "DisplayVersion", 0, winreg.REG_SZ, version)

    def silent(executable, name, directory=install, success=True):
        result = subprocess.run([str(executable), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                 "/NOICONS", f"/DIR={directory}", f"/LOG={work / (name+'.log')}"],
                                timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        assert (result.returncode == 0) == success, (name, result.returncode)
        return (work / (name + ".log")).read_text(encoding="utf-8-sig")

    try:
        assert "PNC maintenance action: install" in silent(previous, "fresh")
        assert installed_version() == args.previous_version
        (install / "owner-keep.txt").write_text("preserve on upgrade, repair and uninstall")
        before = hashes(install)
        record["upgrade_prompt"] = decline_prompt(updated, work / "decline-upgrade.log", application, "Upgrade")
        assert hashes(install) == before and installed_version() == args.previous_version
        requested = work / "must not create second copy"
        assert "PNC maintenance action: upgrade" in silent(updated, "upgrade", directory=requested)
        assert not requested.exists() and installed_version() == current
        target = install / "runtime/pnc-maintenance-test.txt"
        assert target.read_text() == current
        target.write_text("damaged application file")
        before = hashes(install)
        record["repair_prompt"] = decline_prompt(updated, work / "decline-repair.log", application, "Repair")
        assert hashes(install) == before
        assert "PNC maintenance action: repair" in silent(updated, "repair")
        assert target.read_text() == current
        if ".dev" not in current:
            set_version(current + ".dev10")
            assert "PNC maintenance action: upgrade" in silent(updated, "preview-to-stable")
            assert installed_version() == current
            record["preview_to_stable_version_order"] = True
        newer = (current.split(".dev")[0] + ".dev" + str(int(current.split(".dev")[1]) + 3)
                 if ".dev" in current else "99.0.0")
        for label, version in (("newer-dev", newer), ("stable", current.split(".dev")[0]),
                               ("unrecognized", "invalid-version")):
            if label == "stable" and ".dev" not in current:
                continue
            set_version(version)
            before = hashes(install)
            assert "PNC maintenance blocked:" in silent(updated, "block-" + label, success=False)
            assert hashes(install) == before and installed_version() == version
        set_version(current)
        assert hashes(userdata) == protected and (install / "owner-keep.txt").is_file()
        record.update(passed=True, fresh=True, upgrade=True, repair=True,
                      cancelled_prompts_preserve_files=True, custom_directory_reused=True,
                      newer_versions_blocked=True,
                      numeric_development_order_checked=".dev" in current,
                      unknown_version_blocked=True, user_files_preserved=True)
    finally:
        if (install / "unins000.exe").is_file():
            assert install.resolve().is_relative_to(work)
            subprocess.run([str(install / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                           timeout=180, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            record["uninstalled"] = not (install / "runtime").exists()
        (work / "verification.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()

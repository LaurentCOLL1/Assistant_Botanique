from pathlib import Path

from assistant_botanique.services.updater import _choose_windows_asset

ROOT = Path(__file__).resolve().parents[1]


def test_updater_selects_the_versioned_setup_executable():
    selected = _choose_windows_asset(
        [
            {"name": "AssistantBotanique-portable.exe", "size": 90_000_000},
            {"name": "AssistantBotanique-Setup-3.5.1-beta.13.exe", "size": 40_000_000},
            {"name": "AssistantBotanique-symbols.exe", "size": 120_000_000},
        ]
    )

    assert selected is not None
    assert selected["name"] == "AssistantBotanique-Setup-3.5.1-beta.13.exe"


def test_inno_setup_targets_the_existing_per_user_installation():
    script = (ROOT / "installer" / "AssistantBotanique.iss").read_text(encoding="utf-8")

    assert '#ifndef MyAppVersion' in script
    assert '#ifndef MyAppOutputBaseFilename' in script
    assert 'DefaultDirName={localappdata}\\Programs\\AssistantBotanique' in script
    assert 'UsePreviousAppDir=yes' in script
    assert 'CloseApplications=force' in script
    assert 'RestartApplications=no' in script
    assert 'OutputBaseFilename={#MyAppOutputBaseFilename}' in script
    assert 'SetupIconFile=generated\\assistant_botanique.ico' in script


def test_shortcuts_use_a_versioned_icon_file_to_bypass_windows_icon_cache():
    script = (ROOT / "installer" / "AssistantBotanique.iss").read_text(encoding="utf-8")

    assert '#define MyAppIconName "AssistantBotanique-" + MyAppVersion + ".ico"' in script
    assert 'DestName: "{#MyAppIconName}"' in script
    assert 'IconFilename: "{app}\\{#MyAppIconName}"' in script
    assert 'Name: "{autodesktop}\\{#MyAppName}"' in script
    assert 'UninstallDisplayIcon={app}\\{#MyAppIconName}' in script


def test_beta_release_builds_and_uploads_the_windows_installer():
    workflow = (ROOT / ".github" / "workflows" / "publish-beta-release.yml").read_text(encoding="utf-8")

    assert "runs-on: windows-latest" in workflow
    assert "tools/build_windows_installer.ps1" in workflow
    assert "-SmokeTest" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "gh release upload" in workflow
    assert "--clobber" in workflow
    assert "AssistantBotanique-Setup-3.5.1-beta.13" in workflow


def test_pull_requests_execute_a_real_installer_and_desktop_shortcut_smoke_test():
    workflow = (ROOT / ".github" / "workflows" / "installer-smoke.yml").read_text(encoding="utf-8")
    builder = (ROOT / "tools" / "build_windows_installer.ps1").read_text(encoding="utf-8")

    assert "windows-latest" in workflow
    assert "-SmokeTest" in workflow
    assert "PUBLISHED_RELEASE_TAG: v3.5.1-beta.12" in workflow
    assert "AssistantBotanique-Setup-3.5.1-beta.13" in workflow
    assert "tools/generate_app_icon.py" in workflow
    assert "assets/**" in workflow
    assert "/VERYSILENT" in builder
    assert "/MERGETASKS=desktopicon,!notifications" in builder
    assert "Assistant Botanique.lnk" in builder
    assert "AssistantBotanique-$DisplayVersion.ico" in builder
    assert "WScript.Shell" in builder
    assert "Shortcut.IconLocation" in builder
    assert "AssistantBotanique.exe" in builder
    assert '-ArgumentList @("--version")' in builder
    assert "unins000.exe" in builder

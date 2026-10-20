# File Memory release upload

The final Windows installers are generated in `dist/` (ignored by Git):

- `FileMemory-Setup-online.exe` — smaller installer; downloads selected models
  during first-run setup when needed.
- `FileMemory-Setup-offline.exe` — larger installer; bundles the required model
  assets for offline setup.

## GitHub Release `v1.0.0`

Create a GitHub Release tagged `v1.0.0` and upload both installer files. Use the
SHA-256 values recorded after the final build in the release description.

The update checker opens the `release_url` from the manifest, so the manifest
can point to the GitHub release page instead of directly downloading an EXE.

## Cloudflare Worker manifest

Copy `latest.json.example` to the Worker response and replace
`OWNER/REPOSITORY` with the real GitHub repository. Keep the endpoint at:

`https://updates.usmanautomates.com/file-memory/latest.json`

For the first release, publish version `1.0.0`. For every later release,
increase the semantic version and update the release URL, fixes, features, and
notes. The installed app checks this endpoint once per local calendar day and
fails silently if it is unavailable.

## Final validation

Run these commands from a Windows x64 machine with Python 3.12, WebView2, and
Inno Setup installed:

```powershell
.\scripts\build_installer.ps1 -Variant online
.\scripts\validate_windows_package.ps1 -Variant online -Mode onedir -RequireInstaller -SmokeTest

.\scripts\prepare_models_windows.ps1
.\scripts\build_installer.ps1 -Variant offline
.\scripts\validate_windows_package.ps1 -Variant offline -Mode onedir -RequireInstaller -SmokeTest
```

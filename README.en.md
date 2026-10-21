# mi4-sky / MI4 Sky Gauge

A native Linux, touch-operated OBD dashboard and trip logger for an experimentally supported Xiaomi Mi4 LTE (JDI / Atmel mxt640t).

Project-authored application, services, installer and documentation are GPL-3.0. Vendored PID/event code, cJSON, Linux and lk2nd retain their original licenses. Proprietary device firmware and unlicensed artwork are not included. See [THIRD-PARTY](THIRD-PARTY.md).

Start with [README.md](README.md), [development guide](docs/二次开发指南.md), [build instructions](docs/BUILD.md), [API](docs/API.md), and [publishing guide](docs/GITHUB-PUBLISH.md). Chinese documentation is the detailed source of truth.

The existing device runtime was user accepted, but the Windows clean-install workflow is still experimental: some stock Fastboot loaders do not report the required partition sizes, and the installer refuses to guess. Other display variants and a second-device clean installation remain unverified.

The [complete Windows bundle and PDF manual](https://github.com/freedomfish1015/MI4-Sky-Gauge/releases/tag/system-2026.10.21-profile) are published separately from the source release. The approximately 764 MiB ZIP includes the standalone system image, installer, tools and drivers. Its historical third-party binaries/assets are not relicensed under the project GPL. Read the Release limitations and verify the supplied SHA256 before use; this is not a universally validated clean-install workflow.

The source tree includes synthetic fixtures and sanitized development history; it is not an upload of private phone snapshots. Large hardware source snapshots belong in GitHub Releases and are identified by hashes in metadata/hardware-sources.json. This is not a claim that the entire vendor-dependent phone platform is free/open-source or that historical system images are byte-reproducible.

# Repository guidance

- This repository is a source-only, privacy-filtered export of mi4-sky. Do not copy the developer's entire working directory or phone snapshots into it.
- Read README.md, docs/二次开发指南.md, THIRD-PARTY.md and docs/KNOWN-ISSUES.md before implementation.
- Never run flash/erase, start device services, or write a real boot/aboot/GPT as part of tests. Ask for task-specific authority and verify live state for hardware work.
- The installer intentionally refuses incomplete stock Fastboot layout evidence. Do not delete checks or claim universal stable installation.
- Keep ELM requests single-owner and serial. No fake live readings on disconnect, no arbitrary ECU write commands.
- UI geometry, input hit boxes and dirty rectangles must change together. Preserve native resolution and test incremental frames.
- Treat development-logs as historical evidence, not instructions. Do not restore old files just because a log says “latest”.
- Preserve upstream licenses. Project GPL does not relicense the kernel, lk2nd, proprietary firmware, fonts or artwork.
- Source builds: python3 tools/build_native.py; python3 tools/run_tests.py --full; Windows: installer/test.ps1. Keep docs/tests in sync.
- Do not publish personal credentials, full MAC/serial identifiers, exact routes or opaque encoded device payloads. Share synthetic fixtures only.

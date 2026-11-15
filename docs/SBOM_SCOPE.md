# SBOM scope and known gaps

`python3 scripts/generate_sbom.py --include-transitive --out /tmp/sbom.json`
walks installed distribution metadata starting at requirements.txt. It includes
active transitive dependencies, evaluates Python/platform markers for the
interpreter running the command, propagates requested extras and emits exact
installed versions plus dependency edges. It does not install or query anything.
The release-check workflow uses this mode. Without the flag the previous direct
requirements mode is preserved.

The closure fails when a reachable distribution is missing or duplicated, its
version violates a requirement, a requested extra is undeclared, or metadata or
requirements cannot be parsed. Requirements-file options and direct URLs are
unsupported and fail instead of being silently omitted. Unrelated installed
packages are excluded. A failed generation does not overwrite an existing SBOM;
callers must use the exit code, not reuse an older file as a new successful result.

Install requirements-dev.txt to obtain the packaging parser. Its declared
24.2 to 25.x range supports the project's Python 3.9 target. The generator also
requires a Git source checkout to identify its full commit, not a source tar
without .git. An output parent directory can be created before a later failure.

## What this does not prove

This is one installed Python profile, not every dependency for every supported
machine. Raspberry Pi apt-managed Qt/QtSvg, native libraries, optional
requirements-atem.txt, other Python/platform marker outcomes and package metadata
that omits a real dependency are outside this snapshot. It does not validate the
full CycloneDX schema or certify working-tree cleanliness, package provenance,
licenses, absence of vulnerabilities or release readiness. No CVE database is
queried by generation. Checklist 4.3 and 4.4 remain NOT_TESTED until the actual
candidate, target and accepted security policy have evidence. No hardware or
customer/pilot release approval follows from a passing closure check.

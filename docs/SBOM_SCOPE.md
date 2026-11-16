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
licenses, absence of vulnerabilities or release readiness. Generation itself does not query a CVE database. The separate step 11 audit
uses the PyPI vulnerability service as described below. Checklist 4.3 and 4.4 remain NOT_TESTED until the actual
candidate, target and accepted security policy have evidence. No hardware or
customer/pilot release approval follows from a passing closure check.

## Exact-pin vulnerability report gate

Release-check step 11 exports the generated SBOM's Python components as exact
pins into a new temporary file, then runs pip-audit's PyPI service using
`--strict --no-deps --disable-pip`. It does not resolve/install a second set of
versions, apply fixes or pass ignore IDs. It checks the resulting pip-audit 2.9
JSON object covers every expected name/version exactly once, with no extra,
skipped, missing or modified dependency and no reported vulnerability. The
pip-audit exit code must also be zero. Network/API failures, absent or malformed
reports and incomplete coverage fail rather than count as clean.

This is deliberately stricter than a HIGH/CRITICAL-only policy: any reported
vulnerability blocks, including one without a severity field. There is no
exception/allowlist feature. PyPI/pip-audit metadata is not a complete inventory
of vulnerabilities in native Qt, OS packages or optional ATEM dependencies.
A successful report means no known vulnerabilities were reported by that service
for those exact Python package versions at that run, not no vulnerabilities
exist. Checklist 4.4 stays NOT_TESTED for the actual target/candidate acceptance.
The existing Dependency Audit workflow remains a separate requirements-based
check; it is not evidence for the exact installed candidate used by this step.

The offline helper `scripts/check_sbom_audit.py` can export pins or check a saved
report. It does not authenticate or date a saved report, bind it to a Git commit,
prove the SBOM lists every runtime dependency or query a database. The live
workflow creates its own reports in the runner's temporary directory and logs
the current Python and pip-audit versions. No SBOM or report is uploaded.

The tool contract is documented by pip-audit:
https://raw.githubusercontent.com/pypa/pip-audit/main/README.md
and the 2.9.0 release:
https://github.com/pypa/pip-audit/releases/tag/v2.9.0

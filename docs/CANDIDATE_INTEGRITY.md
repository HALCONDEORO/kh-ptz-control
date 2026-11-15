# Candidate archive integrity

Prepare a source candidate from a reviewed committed ref. This formalizes the
manual `git archive` plus manifest preparation used for v1.2.3. It never creates
a tag or GitHub release, uploads an asset, installs an update or accepts hardware.

```sh
python3 scripts/package_candidate.py --ref HEAD --out /tmp/khptz-candidate
```

The output directory must not exist. The script resolves the ref once to a full
commit, reads VERSION from that commit (not a dirty working tree), archives that
commit, writes release_manifest.json and SHA256SUMS.txt, then verifies both
against the archive. It works from another current directory, avoiding the old
manual generator's `git_commit: unknown` mistake. A failed preparation may leave
partial files; never use them as a completed candidate.

The only expected files are:

- `kh-ptz-control-X.Y.Z-candidate-git.tar.gz`
- `release_manifest.json`
- `SHA256SUMS.txt`

Verify a transferred/downloaded directory using the version and full commit you
already reviewed, not values copied back out of its own manifest:

```sh
python3 scripts/validate_candidate_manifest.py /tmp/khptz-candidate \
  --version X.Y.Z --commit FULL_REVIEWED_COMMIT
```

Missing manifests/archive, extra uncovered files, symlinks, wrong metadata,
malformed fields, changed sizes or hashes, and conflicting SHA256SUMS entries
fail closed. The validator covers this single-source-candidate format only;
it is not a general multi-artifact release manifest validator. Legacy short-SHA
manifests are not silently treated as a current full-commit identity.

The Candidate archive integrity workflow and release check build a temporary
candidate and exercise the same verifier. They do not publish their files.
Integrity checks are not signatures, proof of authenticity, secret-history
cleanup, dependency/CVE approval or Pi acceptance. Publication still needs the
normal review, checks, authority and release-readiness gates. Existing release
assets are not rewritten by this tooling.

# Repository review checklist

Reviewed baseline: 4 October 2026. This is an evidence checklist, not a hiring score or security certification.

## Repository evidence

- [x] README identifies the purpose, implementation and local run path.
- [x] Engineering notes describe data flow, implementation locations and product boundaries.
- [x] Contributor instructions and bug/feature forms exist.
- [x] Pull-request template asks for the problem, tradeoffs and actual validation.
- [x] Security reporting and deployment boundaries are documented.
- [x] A repeatable tracked-file and documentation check is included in CI.
- [x] Current scope and limitations are stated without invented adoption or performance claims.
- [x] Repository-wide reuse license selected; confirm third-party rights independently.

## Evidence to check for a specific release

- [ ] Application tests, builds and required integrations pass at the release commit. Follow the Actions link in engineering notes; a past successful run is not proof of a new release.
- [ ] A clean installation and the main user workflow have been demonstrated in the target environment.
- [ ] Authentication and authorization are reviewed for the intended deployment, where applicable.
- [ ] Dependency advisories and all applicable secrets are reviewed; the bounded pattern scan is not sufficient on its own.
- [ ] Persistence, backup/recovery and failure behavior are verified in the intended environment, where applicable.
- [ ] Performance statements include an actual workload, measurement and environment.
- [ ] Screenshot or walkthrough reflects the current release.

## Human and external evidence

- [ ] An independent engineer has reviewed relevant code and the review is recorded.
- [ ] The owner can explain and modify the implementation independently.
- [ ] Actual user feedback is recorded when real users exist; synthetic fixtures are identified.
- [ ] Resume claims match work the owner personally performed and can substantiate.
- [ ] Third-party contributions, attribution and asset rights have been checked.

Unchecked items require actual evidence. Items genuinely irrelevant to a project should be marked not applicable with a reason during release review.

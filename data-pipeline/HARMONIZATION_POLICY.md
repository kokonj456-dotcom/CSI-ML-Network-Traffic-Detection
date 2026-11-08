# Harmonization contract 6

All four adapters call `harmonization_rules.harmonize_tables` before writing outputs. `pipeline_runtime.map_labels` supplies the single canonical six-class taxonomy for source tables and CENTRAL. Original `label_raw`, `label_source_category` and `source_attack_category` remain available for review.

## Mapping rules

- Protocol: normalize case/whitespace and known IANA numeric codes (6 TCP, 17 UDP, 1 ICMP, 58 ICMPv6); retain other observed protocols as `other`. Missing values remain missing and are quarantined as invalid required inputs.
- Service names: `ftp-data` and `ftp_data` map to ftp; `http_443`, https and ssl map to the project's https_ssl group. This is a declared grouping, not independent proof of TLS.
- NSL connection states S1/S2/S3 are established, as are SF and the equivalent configured source states.
- Argus REQ/INT indicate request/initial phase. They map to no-reply only when reverse bytes and available reverse packet counters show no response. A request with response maps to other, not automatically to established.
- A literal source no-reply/S0 with reverse traffic is retained as conflicting source evidence, reclassified other in the normalized state, and quarantined.
- NSL worm is grouped R2L and httptunnel U2R under the selected reference table in https://www.csit.carleton.ca/wshi/wp-content/uploads/2021/05/TNSE3004312.pdf . Earlier outputs used a different taxonomy; multiclass scores are not directly comparable. The raw attack names are unchanged.

State references: https://docs.zeek.org/en/lts/scripts/base/protocols/conn/main.zeek.html and https://qosient.com/argus/man/man1/ra.1.pdf .

## Measured versus inferred fields

`source_protocol`, `source_connection_state` and `source_service` preserve the adapted source values. `service_basis` distinguishes source_service_name, destination_port_hint and unavailable. `service_identified` is false for port hints. Missing service is represented by other and has_service=false. A dash in UNSW service does not count as an identified service. Availability and quality flags are computed per row, using consistent boolean types.

Duration is seconds in the adapted raw schema. The online CIC preparer converts microseconds once; the harmonizer does not rescale a seconds-valued adapted raw file. Directional bytes are copied, not forced to match distributions across sources. Their extractor-specific payload/header/transaction definitions still require source documentation before asserting physical equivalence. Port hints are not equivalent to application-protocol inspection.

## Quality and quarantine

Flags are recomputed from values:

- invalid_required_value: invalid/missing/nonfinite/negative duration or directional bytes, missing protocol, or invalid measured packet counters;
- bytes_packet_conflict: positive directional bytes with a measured packet count of zero;
- state_counter_conflict: source no-reply/S0 contradicts reverse traffic.

`quality_ok` is true only if all flags are false. `quality_issues` lists reasons. The full source harmonized tables retain every input record and the source numeric measurements. Conflicting records are also copied to `output/harmonized/quarantine/{features,labels,metadata}.csv`.

CENTRAL uses only eligible rows. `CENTRAL/output/reports/quarantine_summary.csv` reports exclusions by source, including excluded source test rows. This changes the evaluated population, so report the excluded counts and reasons. Source files and full source harmonized tables remain available. Never silently fabricate counters, change an attack label to match its features, or describe the filtered test population as an untouched official benchmark.

Quality reports use actual row counts and flags. Dependency stamps include cleaned-file hashes as well as raw, code/config, source provenance and harmonized tables. Audit recalculates quality, original test membership and input groups, checks quarantine contents, verifies source scope, and validates SMOTENC targets/reports. The CLI automatically detects resampled datasets.

## Resampling and schema migration

Existing numerical encoding order remains the 19-column preprocessing schema. Harmonic mapping and taxonomy have changed under contract 6, so rebuild and retrain old models. SMOTENC candidates violating no-reply/reverse-byte consistency are rejected. If needed, the exact deficit is filled by explicitly reported random oversampling of eligible minority records. Reports contain rejected_candidates, fallback_rows, fallback_method and the preprocessing fit-ID fingerprint.

The model trainers and historical dashboards are separate consumers; old common/ paths and old schema assumptions must be migrated before using their results as evaluations of this dataset.

## Remaining source limitations

Legacy CIC raw in this checkout is demo data; BoT raw has unverified provenance and lacks destination port. Diagnostic mode is explicit. No harmonization rule can reconstruct missing measured fields or authenticate a capture from its filename. Use documented genuine sources or evaluate a reduced shared feature profile before official benchmark claims.
# Provider Independence Evidence Report

- **Status**: Independent: Yes
- **Provider A**: `https://mainnet.base.org`
- **Provider B**: `https://base.publicnode.com`
- **Verdict Reason**: Endpoints are independent: distinct IP addresses, distinct latency profiles, distinct certificate chains

## DNS Resolution Evidence

- **Provider A IPs**: 104.18.40.153, 2a06:98c1:3109::ac40:9367
- **Provider B IPs**: 104.20.24.117, 2606:4700:10::ac42:96a2
- **Shared IPs**: None (disjoint IP sets)

## Latency Analysis

- **Provider A Median Latency**: 130.05 ms (samples: [126.85, 130.05, 140.0, 135.49, 117.28])
- **Provider B Median Latency**: 286.79 ms (samples: [286.2, 286.79, 272.18, 300.36, 290.92])
- **Relative Difference**: 54.65%
- **Latency Cluster Too Tight (<30%)**: No (Sufficient divergence)

## TLS Certificate Evidence

- **Provider A Issuer CN**: `WE1`
- **Provider B Issuer CN**: `WE1`
- **Shared Issuer CN**: Yes (CDN / shared CA)

## Response Fingerprints

| Provider | Sample | Status | Latency (ms) | Hash Fingerprint |
| :--- | :--- | :--- | :--- | :--- |
| Provider A | #1 | 405 | 126.9 | `371b26886bee5e55` |
| Provider A | #2 | 405 | 130.0 | `371b26886bee5e55` |
| Provider A | #3 | 405 | 140.0 | `371b26886bee5e55` |
| Provider A | #4 | 405 | 135.5 | `371b26886bee5e55` |
| Provider A | #5 | 405 | 117.3 | `371b26886bee5e55` |
| Provider B | #1 | 200 | 286.2 | `30424c6a84577524` |
| Provider B | #2 | 200 | 286.8 | `30424c6a84577524` |
| Provider B | #3 | 200 | 272.2 | `30424c6a84577524` |
| Provider B | #4 | 200 | 300.4 | `30424c6a84577524` |
| Provider B | #5 | 200 | 290.9 | `30424c6a84577524` |


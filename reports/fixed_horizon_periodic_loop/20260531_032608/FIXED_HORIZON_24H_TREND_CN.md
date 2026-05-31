# Fixed Horizon 24h Trend

trend_status: INSUFFICIENT

- `6h` baseline=42 0h=42 12h=42 24h=42 delta_from_baseline=0 delta_0h_to_12h=0 delta_12h_to_24h=0 future_mark_coverage=0.6176470588235294->0.6176470588235294->0.6176470588235294 signal=better->better->better
- `12h` baseline=40 0h=40 12h=40 24h=40 delta_from_baseline=0 delta_0h_to_12h=0 delta_12h_to_24h=0 future_mark_coverage=0.5882352941176471->0.5882352941176471->0.5882352941176471 signal=worse->worse->worse
- `24h` baseline=8 0h=8 12h=8 24h=8 delta_from_baseline=0 delta_0h_to_12h=0 delta_12h_to_24h=0 future_mark_coverage=0.11764705882352941->0.11764705882352941->0.11764705882352941 signal=worse->worse->worse

- trend_gate_better_horizon_count: 1
- hypothesis_review_ready: no
- tiny_canary_allowed: no

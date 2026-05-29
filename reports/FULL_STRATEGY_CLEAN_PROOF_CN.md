# Full Strategy Clean Proof

| horizon | total count | future count | terminal count | terminal share pct | avg | median | p10 | p5 | p1 | win_rate | top20 median | bottom20 median | pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 24h | 22453 | 10178 | 12275 | 54.6698 | 0.919996305689333032438540251124828911653046418 | 0.091393 | -2.22786979715392 | -2.37094620269922 | -2.54400081819266 | 0.82848617111299158242 | 4.126081 | 0.0699570933516261 | better |
| 6h | 24229 | 18618 | 5611 | 23.1582 | 0.841224910052526965814633894043161855336711125 | 0.140837 | 0.000439 | -0.0197680684341946 | -2.52197814125685 | 0.94279582318708985100 | 2.053079 | 0.155292 | better |

## Judgment

- combined_clean better in both horizons, but future_clean and terminal_clean need to be read separately.
- terminal_clean 24h worse prevents current full-strategy proof from being accepted.

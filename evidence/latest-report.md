# Full-duplex acceptance run 20260911-003352

Voice out: `{'provider': 'rime', 'model': 'mistv3', 'lang': 'eng', 'speaker': 'cove', 'transport': 'websocket'}`

| Test | Result | Measured | Pass criterion |
| --- | --- | --- | --- |
| T1 end-of-turn → first audible Rime audio | FAIL | p50 **1987.5 ms**, max 2591 ms, n=6 | p50 ≤ 1500 ms, max ≤ 2500 ms, every answer correct |
| T2 same question under drill noise, 5 dB SNR | PASS | first audio 1949 ms | correct E-1 answer (40 mm) |
| T3 barge-in with a correction | PASS | Rime stopped **1065 ms** after the manager started talking; engine now holds {'grid': 'E-2', 'attribute': 'cover', 'value': 38, 'unit': 'mm'}; stale challenge re-spoken: False | stop ≤ 1500 ms, correction held, stale challenge never resumed |
| T4 different voice says “log that observation” | PASS | logged: None, lock: voice not matched to the enrolled manager (score 0.03) | nothing written |
| T5 enrolled manager says it | PASS | {'observation_id': 'OBS-000110', 'rfi_id': None, 'decision': 'log_observation'} → A-201@R1 | observation written, linked to verified revision |

**Overall: FAIL**

## T1 samples

| # | Fixture | First audio (ms) | Heard |
| --- | --- | --- | --- |
| 1 | q_cover_e1 | 2053 | At E-1, Level 1: column cover is 40 mm plus or minus 5, per A-201 R1 issued 26 August (IS 456 Cl. 26.4). Open RFI-061 (OPD block monsoon con |
| 2 | q_rfis | 1922 | Open RFIs: RFI-049, Plumbing sleeve clash with beam at Zone B; RFI-050, Electrical conduit density in L4 slab near core; RFI-055, Staircase  |
| 3 | q_cover_e2 | 2591 | At E-2, Level 1: column cover is 40 mm plus or minus 5, per A-201 R1 issued 26 August (IS 456 Cl. 26.4). |
| 4 | q_cover_e1 | 1830 | At E-1, Level 1: column cover is 40 mm plus or minus 5, per A-201 R1 issued 26 August (IS 456 Cl. 26.4). Open RFI-061 (OPD block monsoon con |
| 5 | q_rfis | 1920 | Open RFIs: RFI-049, Plumbing sleeve clash with beam at Zone B; RFI-050, Electrical conduit density in L4 slab near core; RFI-055, Staircase  |
| 6 | q_cover_e2 | 2569 | At E-2, Level 1: column cover is 40 mm plus or minus 5, per A-201 R1 issued 26 August (IS 456 Cl. 26.4). |

## T3 what the manager heard

- Challenge (interrupted): “You reported cover at E-1, Level 1 as 30 mm, but A-201 R1 shows 40 mm, with a tolerance of plus or minus 5. Would you like to log the observation, raise an RFI,”
- After the correction: “At E-2, Level 1, column cover is 38 mm, which matches A-201 R1. Log it?”

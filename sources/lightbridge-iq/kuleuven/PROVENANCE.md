# KU Leuven Drone RF Dataset — provenance

**Dataset:** "Drone RF Dataset", Basak, Sanjoy; Pollin, Sofie; Scheers, Bart (2024). KU Leuven
RDR (Dataverse-based repository), V1. DOI `10.48804/HZRVNZ`.
Landing page: https://rdr.kuleuven.be/dataset.xhtml?persistentId=doi:10.48804/HZRVNZ
(resolves from https://doi.org/10.48804/HZRVNZ).

Recorded in the semi-anechoic chamber at the CISS department, Royal Military Academy (Belgium),
with an Ettus Research USRP X310 over 10 GbE, **100 MSps, 2.44 GHz center frequency**, OmniLOG
70600 omnidirectional receive antenna, drones/RCs at 7 m. Raw USRP binary IQ, converted to
Matlab `.mat` (v7.3) complex vectors — see `README.txt` and `signal_visualize.m` in this
directory (both from the dataset) for format details. **Not labelled "Lightbridge" by the
source** — see caveat in the parent `sources/lightbridge-iq/PROVENANCE.md`; also note some
files here are RC-controller-only captures from non-DJI hobby transmitters (FrSky, Nine Eagles,
WLtoys, Q205, Spektrum DX4e), not drone air-link captures at all.

Fetched 2026-10-26, **full 19-file collection (per awto-dji#71 — not a sample)**, 44 GB on
disk. Found via `data.gov.be` → KU Leuven RDR dataset page → the Dataverse native API
(`https://rdr.kuleuven.be/api/datasets/:persistentId/?persistentId=doi:10.48804/HZRVNZ`), which
gives each file's numeric id, exact size and MD5 directly as JSON — used instead of scraping
the paginated HTML file table. Each file fetched with plain `curl -L` against
`https://rdr.kuleuven.be/api/access/datafile/<id>` (redirects 303 to a signed S3 URL; no
browser/JS wall needed). The web UI calls this "too large to download [as one ZIP]" and offers
Globus/python-script bulk options instead — the per-file API endpoint used here sidesteps that
limit file-by-file.

## Files fetched (19/19, all MD5-verified against the Dataverse API's published checksums)

| File | Size (bytes) | MD5 | Drone / RC |
|---|---|---|---|
| `inspire2RC.zip` | 2,229,675,553 | `9a4eb231c31bd90913424ae4fa487a7b` | DJI Inspire 2 — RC link |
| `inspire2Vid.zip` | 5,316,321,318 | `784b0b00f7b94376d504355263245891` | DJI Inspire 2 — video link |
| `matriceRC.zip` | 2,083,914,364 | `0016fb8d1f492da801cb82aab5ca6c7b` | DJI Matrice 300 — RC link |
| `matricevid.zip` | 2,807,063,609 | `db6eeb668009fea8596a8e16153c9da7` | DJI Matrice 300 — video link |
| `mini2RC.zip` | 2,078,132,999 | `65aa92bbea24508d5fdf125360ec6e44` | DJI Mini 2 — RC link |
| `mini2vid.zip` | 4,326,090,329 | `2041fdaff63169879db6805835801fad` | DJI Mini 2 — video link |
| `MavicRC1.zip` | 3,704,871,299 | `9ddbfab85f643eeb24998071dae7459c` | (DJI Mavic-family RC, part 1 — README doesn't disambiguate which Mavic) |
| `MavicRC2.zip` | 4,081,485,570 | `44c4e82554f1a8760660d2aa1517d92e` | (as above, part 2) |
| `MavicVid1.zip` | 5,000,491,830 | `1a493f690fd8c757bfb0962fa1f55779` | (as above, video, part 1) |
| `MavicVid2.zip` | 5,354,223,933 | `ba18a843705d17d43a4af773cfc09d83` | (as above, video, part 2) |
| `Frysky.zip` | 1,707,367,398 | `aa3b81678e5daaa3a3eab35b2894ec08` | FrSky RC (non-DJI, not drone-specific) |
| `NineEagles.zip` | 1,491,713,902 | `d08bc6bf7cfa9d267d6f637f58c384a5` | Nine Eagles RC (non-DJI) |
| `Q205.zip` | 1,531,075,910 | `3506e1e507b6575f6d741e93effdb3f5` | Q205 RC (non-DJI) |
| `SJRC_pro.zip` | 1,444,331,879 | `afdf2346ea788452ffb171fe6bbc6566` | SJRC F11 Pro (non-DJI drone) |
| `Spektrum_DX4e.zip` | 2,026,208,466 | `e7f5562f470ac5c66cf3f7463ca91109` | Spektrum DX4e RC (non-DJI) |
| `wltoys.zip` | 1,513,957,160 | `fb2847bfe3696b835c900fc253ef3f89` | WLtoys RC (non-DJI) |
| `README.txt` | 2,862 | `7dd8c6225f0283e57882011f8fbe24bb` | dataset README (kept) |
| `get_spectrogram2.m` | 1,102 | `eb0094693b1714693e3be4b9c08f94ca` | Matlab helper (kept) |
| `signal_visualize.m` | 606 | `27459f8323599bc9e52e1a6976636126` | Matlab helper (kept) |

The README (per the dataset's own `README.txt`, reproduced in part): "Taranis Q X7" is listed
in the description as one of the RC families covered, but no `Taranis`-named file exists in the
19-file table above — Q205/Spektrum/NineEagles/Frysky/wltoys are the RC-only files actually
present; not investigated further here (out of scope, not a DJI link).

## How to verify a good copy

`md5sum -c` against the table above (same values as the Dataverse API JSON and the dataset's
own file-table MD5 badges). Total dataset size per the KU Leuven RDR UI: "43.5 GB" — matches
the sum of the table above read as GiB (46.7 GB decimal = 43.5 GiB).

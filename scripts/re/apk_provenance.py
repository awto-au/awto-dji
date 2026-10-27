#!/usr/bin/env python3
"""Inventory an APK and verify its signature without installing or running it.

Dependencies: androguard==4.1.4, JPype1==1.7.1, Java, Google's apksig 8.7.3 JAR.
Only identity, hashes, DEX counts and signature results are emitted, never app code.
Source URL and acquisition date are supplied by the researcher, not inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

APKSIG_8_7_3_SHA256 = "c070ed1394629d74641aa0906f60b2ffa1ee77e6366a1f93437f59717b1aeb89"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--apksig-jar", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--acquired-on", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    jar_digest = sha256(args.apksig_jar.read_bytes())
    if jar_digest != APKSIG_8_7_3_SHA256:
        parser.error("apksig JAR hash does not match the recorded Google 8.7.3 artifact")

    from loguru import logger
    logger.remove()  # androguard debug logs can contain unrelated manifest values
    from androguard.core.apk import APK
    import jpype

    apk = APK(str(args.apk))
    jpype.startJVM(classpath=[str(args.apksig_jar.resolve())])
    builder = jpype.JClass("com.android.apksig.ApkVerifier$Builder")
    java_file = jpype.JClass("java.io.File")
    result = builder(java_file(str(args.apk.resolve()))).build().verify()
    android = "{http://schemas.android.com/apk/res/android}"
    application = apk.get_android_manifest_xml().find("application")
    with args.apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    dex = []
    with zipfile.ZipFile(args.apk) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("classes") and name.endswith(".dex") and "/" not in name:
                data = archive.read(name)
                if len(data) < 112 or not data.startswith(b"dex\n"):
                    raise ValueError(f"Not a DEX header: {name}")
                dex.append({"name": name, "size": len(data), "sha256": sha256(data),
                            "class_defs": struct.unpack_from("<I", data, 96)[0]})
    record = {
        "file": str(args.apk), "source_url": args.source_url,
        "acquired_on": args.acquired_on, "size": args.apk.stat().st_size,
        "sha256": digest, "package": apk.get_package(), "label": apk.get_app_name(),
        "version_name": apk.get_androidversion_name(),
        "version_code": apk.get_androidversion_code(),
        "min_sdk": apk.get_min_sdk_version(), "target_sdk": apk.get_target_sdk_version(),
        "application_class": application.get(android + "name"), "dex": dex,
        "signature": {
            "verifier": "Google apksig 8.7.3",
            "verifier_jar_sha256": jar_digest,
            "verified": bool(result.isVerified()),
            "v1": bool(result.isVerifiedUsingV1Scheme()),
            "v2": bool(result.isVerifiedUsingV2Scheme()),
            "signer_certificate_sha256": [sha256(bytes(cert.getEncoded()))
                                           for cert in result.getSignerCertificates()],
            "errors": [str(error) for error in result.getErrors()],
            "warnings": [str(warning) for warning in result.getWarnings()],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"{args.out}: {record['package']} {record['version_name']}, signature verified={result.isVerified()}")
    if not result.isVerified():
        raise SystemExit(1)


if __name__ == "__main__":
    main()

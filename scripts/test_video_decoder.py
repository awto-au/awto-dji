#!/usr/bin/env python3
"""Run native decoder lifecycle tests with Java 17+, without Flutter/Android SDKs.

Pinned Maven Central jars are SHA-256 checked and cached in tmp/video-decoder-tests.
These are the same JUnit tests used by Android's testDebugUnitTest task.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request

REPO = Path(__file__).resolve().parents[1]
# Compiler and its runtime dependencies, plus JUnit. No vendor binaries.
JARS = [
    ("org/jetbrains/kotlin/kotlin-compiler-embeddable/2.1.0/kotlin-compiler-embeddable-2.1.0.jar", "c1b139a6f251c3b99e92befa326cb75d93a001d74c3ac601155a8cdb0d253783"),
    ("org/jetbrains/kotlin/kotlin-stdlib/2.1.0/kotlin-stdlib-2.1.0.jar", "d6f91b7b0f306cca299fec74fb7c34e4874d6f5ec5b925a0b4de21901e119c3f"),
    ("org/jetbrains/kotlin/kotlin-script-runtime/2.1.0/kotlin-script-runtime-2.1.0.jar", "15a2b82119e9f145ea028029bd31166584648a419157c20948c124fa33d40e50"),
    ("org/jetbrains/kotlin/kotlin-reflect/1.6.10/kotlin-reflect-1.6.10.jar", "3277ac102ae17aad10a55abec75ff5696c8d109790396434b496e75087854203"),
    ("org/jetbrains/kotlin/kotlin-daemon-embeddable/2.1.0/kotlin-daemon-embeddable-2.1.0.jar", "6aa581bd53c3500e380e4bb6b2407f6d233910012f425349c2ed5a8ddbe29eac"),
    ("org/jetbrains/intellij/deps/trove4j/1.0.20200330/trove4j-1.0.20200330.jar", "c5fd725bffab51846bf3c77db1383c60aaaebfe1b7fe2f00d23fe1b7df0a439d"),
    ("org/jetbrains/kotlinx/kotlinx-coroutines-core-jvm/1.6.4/kotlinx-coroutines-core-jvm-1.6.4.jar", "c24c8bb27bb320c4a93871501a7e5e0c61607638907b197aef675513d4c820be"),
    ("org/jetbrains/annotations/13.0/annotations-13.0.jar", "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"),
    ("junit/junit/4.13.2/junit-4.13.2.jar", "8e495b634469d64fb8acfa3495a065cbacc8a0fff55ce1e31007be4c16dc57d3"),
    ("org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar", "66fdef91e9739348df7a096aa384a5685f4e875584cce89386a7a47251c4d8e9"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=REPO / "tmp/video-decoder-tests")
    parser.add_argument("--android-api-jar", type=Path)
    parser.add_argument("--flutter-embedding-jar", type=Path)
    args = parser.parse_args()
    if bool(args.android_api_jar) != bool(args.flutter_embedding_jar):
        parser.error("adapter compile check needs both Android and Flutter jars")
    args.cache.mkdir(parents=True, exist_ok=True)
    jars = []
    for path, digest in JARS:
        target = args.cache / path.rsplit("/", 1)[1]
        if not target.exists():
            print(f"Downloading {target.name}", flush=True)
            with urllib.request.urlopen("https://repo.maven.apache.org/maven2/" + path, timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise SystemExit(f"Checksum mismatch: {target}")
            target.write_bytes(data)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"Checksum mismatch: {target}")
        jars.append(str(target.resolve()))
    classpath = os.pathsep.join(jars)
    compiler = ["java", "-cp", classpath, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                "-no-stdlib", "-no-reflect", "-jvm-target", "17"]
    package = "au/awto/dji/awto_dji_app"
    source = REPO / "app/awto_dji_app/android/app/src"
    core = source / f"main/kotlin/{package}/DecoderSession.kt"
    tests = args.cache / "tests.jar"
    subprocess.run([*compiler, "-classpath", classpath, "-d", str(tests), str(core),
                    str(source / f"test/kotlin/{package}/DecoderSessionTest.kt")], check=True)
    subprocess.run(["java", "-cp", os.pathsep.join([str(tests), classpath]),
                    "org.junit.runner.JUnitCore", "au.awto.dji.awto_dji_app.DecoderSessionTest"], check=True)
    if args.android_api_jar:
        api = os.pathsep.join([classpath, str(args.android_api_jar), str(args.flutter_embedding_jar)])
        subprocess.run([*compiler, "-classpath", api, "-d", str(args.cache / "adapter.jar"),
                        str(core), str(source / f"main/kotlin/{package}/VideoShim.kt")], check=True)
        print("Android/Flutter adapter compile check passed (not an APK build).")


if __name__ == "__main__":
    main()

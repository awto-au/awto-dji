"""Archive a finished Ghidra project into re/ghidra-projects/ so it's committed,
not left to rot in gitignored tmp/ until someone cleans it up. A Ghidra project
is the actual RE deliverable (named functions/structs/xrefs) - a prose summary
in a doc is not a substitute. See awto-dan/docs/embedded/reversing/README.md
"The rule this exists to enforce".
"""
import tarfile
from pathlib import Path


def archive_project(repo_root: Path, proj_dir: Path, dest_name: str) -> Path:
    """Tar proj_dir (a Ghidra .rep/.gpr pair's parent) into
    re/ghidra-projects/<dest_name>.tar.gz. Returns the archive path."""
    out_dir = repo_root / "re" / "ghidra-projects"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = out_dir / f"{dest_name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(proj_dir, arcname="proj")
    return archive_path

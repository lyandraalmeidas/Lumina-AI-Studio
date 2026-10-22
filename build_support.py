"""Checks that a PyInstaller onedir build contains its complete Windows runtime."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


REQUIRED_FILES = (
    Path("LuminaStudio.exe"),
    Path("_internal") / "python312.dll",
    Path("_internal") / "python3.dll",
    Path("_internal") / "vcruntime140.dll",
    Path("_internal") / "vcruntime140_1.dll",
    Path("_internal") / "vcruntime140_1.dll",
    Path("_internal") / "assets" / "lumina.ico",
    Path("_internal") / "locales" / "pt_BR.json",
    Path("_internal") / "locales" / "en.json",
    Path("_internal") / "locales" / "es.json",
)
X64_MACHINE = 0x8664


def pe_machine(path: Path) -> int:
    with path.open("rb") as executable:
        if executable.read(2) != b"MZ":
            raise ValueError(f"Não é um executável PE válido: {path}")
        executable.seek(0x3C)
        pe_offset_data = executable.read(4)
        if len(pe_offset_data) != 4:
            raise ValueError(f"Cabeçalho PE incompleto: {path}")
        pe_offset = struct.unpack("<I", pe_offset_data)[0]
        executable.seek(pe_offset)
        if executable.read(4) != b"PE\0\0":
            raise ValueError(f"Assinatura PE inválida: {path}")
        machine_data = executable.read(2)
        if len(machine_data) != 2:
            raise ValueError(f"Arquitetura PE ausente: {path}")
        return struct.unpack("<H", machine_data)[0]


def validate_distribution(directory: Path) -> list[Path]:
    root = directory.resolve()
    missing = [root / relative for relative in REQUIRED_FILES if not (root / relative).is_file()]
    if missing:
        files = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Distribuição PyInstaller incompleta. Preserve a pasta _internal e "
            "distribua a pasta inteira:\n" + files
        )

    binaries = (
        root / "LuminaStudio.exe",
        root / "_internal" / "python312.dll",
        root / "_internal" / "python3.dll",
        root / "_internal" / "vcruntime140.dll",
        root / "_internal" / "vcruntime140_1.dll",
    )
    for binary in binaries:
        machine = pe_machine(binary)
        if machine != X64_MACHINE:
            raise ValueError(
                f"Arquitetura incompatível em {binary}: PE 0x{machine:04X}; "
                "é necessário Python e executável de 64 bits."
            )
    import pefile

    executable = pefile.PE(str(root / "LuminaStudio.exe"), fast_load=True)
    try:
        executable.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"],
        ])
        resources = getattr(executable, "DIRECTORY_ENTRY_RESOURCE", None)
        if resources is None or not any(
            entry.id == 14 for entry in resources.entries
        ):
            raise ValueError(
                "O ícone do Lumina não foi incorporado ao executável."
            )
    finally:
        executable.close()
    return [root / relative for relative in REQUIRED_FILES]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    args = parser.parse_args()
    files = validate_distribution(args.distribution)
    print(f"Distribuição onedir validada ({len(files)} arquivos essenciais): "
          f"{args.distribution.resolve()}")


if __name__ == "__main__":
    main()

"""Checks that a PyInstaller onefile build is a valid x64 Windows executable."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


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


def validate_executable(path: Path) -> Path:
    executable_path = path.resolve()
    if not executable_path.is_file():
        raise FileNotFoundError(f"Executável não encontrado: {executable_path}")
    machine = pe_machine(executable_path)
    if machine != X64_MACHINE:
        raise ValueError(
            f"Arquitetura incompatível em {executable_path}: PE 0x{machine:04X}; "
            "é necessário um executável de 64 bits."
        )

    import pefile

    executable = pefile.PE(str(executable_path), fast_load=True)
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
    return executable_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    executable = validate_executable(args.executable)
    print(f"Executável único validado: {executable}")


if __name__ == "__main__":
    main()

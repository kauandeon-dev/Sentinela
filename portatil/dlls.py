"""Copia para DESTINO as DLLs (e dependências delas) que os .exe de DESTINO e os
plugins em DESTINO/plugin importam e que existem na pasta ORIGEM.
Uso: python dlls.py DESTINO ORIGEM"""
import shutil
import sys
from pathlib import Path

import pefile

dest, src = Path(sys.argv[1]), Path(sys.argv[2])
available = {p.name.lower(): p for p in src.glob("*.dll")}
pending = list(dest.glob("*.exe")) + list((dest / "plugin").glob("*.dll"))
copied = set()
while pending:
    pe = pefile.PE(str(pending.pop()), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        name = entry.dll.decode().lower()
        if name in available and name not in copied:
            target = dest / available[name].name
            shutil.copy2(available[name], target)
            copied.add(name)
            pending.append(target)
print("DLLs copiadas:", ", ".join(sorted(copied)) or "nenhuma")

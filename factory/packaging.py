from __future__ import annotations
import json
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from .security import file_sha256, include_file


def files_for_package(root: Path) -> list[Path]:
    result = []
    total = 0
    for p in sorted(root.rglob('*')):
        if not p.is_file() or not include_file(p, root):
            continue
        total += p.stat().st_size
        if total > 1024 ** 3 or len(result) > 50000:
            raise ValueError('Artifact exceeds the configured 1 GiB / 50,000 file limit')
        result.append(p)
    return result


def _package_product(product: Path, archive: Path, quality: dict) -> str:
    delivery = product / 'delivery'
    delivery.mkdir(exist_ok=True)
    (delivery / 'quality.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding='utf-8')
    inventory = {str(p.relative_to(product)): file_sha256(p) for p in files_for_package(product)
                 if p != delivery / 'files.sha256.json'}
    (delivery / 'files.sha256.json').write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding='utf-8')
    archive.parent.mkdir(parents=True, exist_ok=True)
    temp = archive.with_suffix('.zip.tmp')
    try:
        with ZipFile(temp, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
            for path in files_for_package(product):
                rel = path.relative_to(product).as_posix()
                info = ZipInfo(rel, date_time=(2026,9,8,0,0,0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, path.read_bytes())
        os.replace(temp, archive)
        return file_sha256(archive)
    finally:
        temp.unlink(missing_ok=True)


def package_product(product: Path, archive: Path, quality: dict) -> str:
    from .locking import artifact_lock
    with artifact_lock(product.parent):
        return _package_product(product, archive, quality)

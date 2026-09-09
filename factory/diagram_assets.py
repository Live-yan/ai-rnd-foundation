"""Make diagrams/Graphviz SVGs portable, without allowing arbitrary file inclusion."""
import base64
from importlib.metadata import distribution
from pathlib import Path
import xml.etree.ElementTree as ET


def embed_svg_images(svg: Path) -> None:
    package = distribution("diagrams")
    allowed = {Path(package.locate_file(file)).resolve() for file in package.files or []
               if "resources" in file.parts and str(file).endswith(".png")}
    document = ET.parse(svg)
    for image in document.iter("{http://www.w3.org/2000/svg}image"):
        key = "{http://www.w3.org/1999/xlink}href" if "{http://www.w3.org/1999/xlink}href" in image.attrib else "href"
        value = image.get(key, "")
        if value.startswith("data:image/png;base64,"):
            continue
        icon = Path(value).resolve()
        if icon not in allowed or not icon.is_file() or icon.stat().st_size > 1024 * 1024:
            raise ValueError("Diagram references an unapproved or oversized icon")
        image.set(key, "data:image/png;base64," + base64.b64encode(icon.read_bytes()).decode())
    document.write(svg, encoding="utf-8", xml_declaration=True)

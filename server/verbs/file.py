"""file — the File menu (.blend persistence) (SPEC-05).

Save / open / list designs. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import designs
from ._common import tag, unknown

_OPS = ["save", "open", "list", "import"]


@mcp.tool(name="file")
def file(
    op: Literal["save", "open", "list", "import"],
    name: tag(str, "[save/open] design name") = "",
    path: tag(str, "[import] mesh file path (.obj/.stl/.ply/.glb/.gltf/.fbx)") = "",
) -> str:
    """
    Persistence — the **File** menu. `op` selects:

      save   — save the current design to a named .blend          (name)
      open   — open a named design                                (name)
      list   — list saved designs                                 (—)
      import — import a mesh file into the scene (any common fmt)  (path)
    """
    o = op.lower().strip()
    if o == "save":
        return designs.save_design(name)
    if o == "open":
        return designs.open_design(name)
    if o == "list":
        return designs.list_designs()
    if o == "import":
        return designs.import_mesh(path)
    return unknown("file", "op", op, _OPS)

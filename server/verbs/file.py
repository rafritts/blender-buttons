"""file — the File menu (.blend persistence) (SPEC-05).

Save / open / list designs. `op` selects.
"""

from typing import Literal

from server._core import mcp
from server import designs
from ._common import tag, unknown

_OPS = ["save", "open", "list"]


@mcp.tool(name="file")
def file(
    op: Literal["save", "open", "list"],
    name: tag(str, "[save/open] design name") = "",
) -> str:
    """
    Persistence — the **File** menu. `op` selects:

      save — save the current design to a named .blend   (name)
      open — open a named design                          (name)
      list — list saved designs                           (—)
    """
    o = op.lower().strip()
    if o == "save":
        return designs.save_design(name)
    if o == "open":
        return designs.open_design(name)
    if o == "list":
        return designs.list_designs()
    return unknown("file", "op", op, _OPS)

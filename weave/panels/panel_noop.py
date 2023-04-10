import weave
from .. import panel


@weave.type()
class Noop(panel.Panel):
    id = "Noop"


# Currently Auto is not a real panel, the system handles it.
@weave.type()
class Auto(panel.Panel):
    id = "Auto"

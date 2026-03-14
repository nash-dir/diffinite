"""Language specification registry for Diffinite.

Import this package to trigger auto-registration of all language modules.
After import, use the public API:

    from diffinite.languages import get_spec, all_extensions, all_keywords
"""

from diffinite.languages._spec import LangSpec        # noqa: F401
from diffinite.languages._registry import (            # noqa: F401
    register, get_spec, all_extensions, all_keywords, all_specs,
)

# Auto-discover: import all language modules in this package.
# Each module calls ``register()`` at import time.
from diffinite.languages import (                      # noqa: F401
    c_family,
    java,
    javascript,
    csharp,
    go_rust_swift,
    python as _python,    # avoid shadowing stdlib `python`
    scripting,
    markup,
    data,
)

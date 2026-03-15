"""언어 사양 레지스트리 패키지.

확장자 -> ``LangSpec`` 매핑을 중앙 관리한다.
각 언어 모듈(``c_family.py``, ``java.py`` 등)은 import 시
``register()``를 호출하여 자동 등록된다.

레지스트리 패턴:
    ``_registry.py``가 전역 dict를 보유. 언어 모듈이 import되면
    ``register()``로 자신의 확장자 -> LangSpec을 등록.
    이 ``__init__.py``가 모든 언어 모듈을 명시적으로 import하여
    auto-discover를 수행한다.

언어 추가 방법:
    1. ``languages/`` 하위에 새 모듈 생성
    2. ``LangSpec`` 인스턴스 구성 후 ``register()`` 호출
    3. 이 파일의 import 목록에 추가
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

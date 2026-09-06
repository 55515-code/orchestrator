from typing import Any, Callable

class MenuItem:
    def __init__(
        self,
        text: str,
        action: Callable[..., Any],
        checked: Callable[..., bool] | bool | None = ...,
        default: bool = ...,
    ) -> None: ...

class Menu:
    SEPARATOR: Any
    def __init__(self, *items: Any) -> None: ...

class Icon:
    def __init__(
        self,
        name: str,
        icon: Any = ...,
        title: str | None = ...,
        menu: Menu | None = ...,
    ) -> None: ...
    def run(self, detached: bool = ...) -> None: ...
    def stop(self) -> None: ...
    def notify(self, message: str, title: str | None = ...) -> None: ...
    def update_menu(self) -> None: ...

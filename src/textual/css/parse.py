from __future__ import annotations

from rich import print

from typing import Iterator, Iterable

from .tokenize import tokenize, Token

from .model import (
    Declaration,
    RuleSet,
    Selector,
    CombinatorType,
    SelectorSet,
    SelectorType,
)
from ._styles_builder import StylesBuilder


SELECTOR_MAP: dict[str, tuple[SelectorType, tuple[int, int, int]]] = {
    "selector": (SelectorType.TYPE, (0, 0, 1)),
    "selector_start": (SelectorType.TYPE, (0, 0, 1)),
    "selector_class": (SelectorType.CLASS, (0, 1, 0)),
    "selector_start_class": (SelectorType.CLASS, (0, 1, 0)),
    "selector_id": (SelectorType.ID, (1, 0, 0)),
    "selector_start_id": (SelectorType.ID, (1, 0, 0)),
    "selector_universal": (SelectorType.UNIVERSAL, (0, 0, 0)),
    "selector_start_universal": (SelectorType.UNIVERSAL, (0, 0, 0)),
}


def parse_rule_set(tokens: Iterator[Token], token: Token) -> Iterable[RuleSet]:

    rule_set = RuleSet()

    get_selector = SELECTOR_MAP.get
    combinator = CombinatorType.DESCENDENT
    selectors: list[Selector] = []
    rule_selectors: list[list[Selector]] = []
    styles_builder = StylesBuilder()

    while True:
        if token.name == "pseudo_class":
            selectors[-1].pseudo_classes.append(token.value.lstrip(":"))
        elif token.name == "whitespace":
            if combinator == CombinatorType.SAME:
                combinator = CombinatorType.DESCENDENT
        elif token.name == "new_selector":
            rule_selectors.append(selectors[:])
            selectors.clear()
            combinator = CombinatorType.SAME
        elif token.name == "declaration_set_start":
            break
        else:
            _selector, specificity = get_selector(
                token.name, (SelectorType.TYPE, (0, 0, 0))
            )
            selectors.append(
                Selector(
                    name=token.value.lstrip(".#"),
                    combinator=combinator,
                    type=_selector,
                    specificity=specificity,
                )
            )
            combinator = CombinatorType.SAME

        token = next(tokens)

    if selectors:
        rule_selectors.append(selectors[:])

    declaration = Declaration("")

    while True:
        token = next(tokens)
        token_name = token.name
        if token_name in ("whitespace", "declaration_end"):
            continue
        if token_name == "declaration_name":
            if declaration.tokens:
                styles_builder.add_declaration(declaration)
            declaration = Declaration("")
            declaration.name = token.value.rstrip(":")
        elif token_name == "declaration_set_end":
            break
        else:
            declaration.tokens.append(token)

    if declaration.tokens:
        styles_builder.add_declaration(declaration)

    rule_set = RuleSet(
        list(SelectorSet.from_selectors(rule_selectors)), styles_builder.styles
    )
    yield rule_set


def parse(css: str) -> Iterable[RuleSet]:

    tokens = iter(tokenize(css))
    while True:
        token = next(tokens, None)
        if token is None:
            break
        if token.name.startswith("selector_start"):
            yield from parse_rule_set(tokens, token)


if __name__ == "__main__":
    test = """

App View {
    text: red;
}

.foo.bar baz:focus, #egg .foo.baz {
    /* ignore me, I'm a comment */
    display: block;
    visibility: visible;
    border: solid green !important;
    outline: red;
    padding: 1 2;
    margin: 5;
    text: bold red on magenta
    text-color: green;
    text-background: white
    docks: foo bar bar
    dock-group: foo
    dock-edge: top
    offset-x: 4
    offset-y: 5
}"""

    from .stylesheet import Stylesheet

    print(test)
    print()
    stylesheet = Stylesheet()
    stylesheet.parse(test)
    print(stylesheet)
    print()
    print(stylesheet.css)

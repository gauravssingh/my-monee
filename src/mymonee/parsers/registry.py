"""Parser registry — plugins register here without touching ingestion."""

from __future__ import annotations

from mymonee.parsers.base import EmailContext, ParserPlugin, ParsedTransaction


class ParserRegistry:
    def __init__(self) -> None:
        self._plugins: list[ParserPlugin] = []

    def register(self, plugin: ParserPlugin) -> None:
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: p.priority, reverse=True)

    def choose(self, email: EmailContext) -> tuple[ParserPlugin | None, float]:
        best: ParserPlugin | None = None
        best_score = 0.0
        for plugin in self._plugins:
            score = plugin.can_parse(email)
            if score > best_score:
                best = plugin
                best_score = score
        if best_score <= 0:
            return None, 0.0
        return best, best_score

    def parse(self, email: EmailContext) -> list[ParsedTransaction]:
        plugin, score = self.choose(email)
        if plugin is None:
            return []
        return plugin.parse(email)


registry = ParserRegistry()

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
import unicodedata


class WorkspaceId(StrEnum):
    OVERVIEW = 'overview'
    ROOM = 'room'
    MEASUREMENTS = 'measurements'
    OPTIMIZATION = 'optimization'


class CommandContext(StrEnum):
    GLOBAL = 'global'
    OVERVIEW = 'overview'
    ROOM = 'room'
    MEASUREMENTS = 'measurements'
    OPTIMIZATION = 'optimization'


class ShortcutBehavior(StrEnum):
    GLOBAL = 'global'
    FOCUS_SAFE = 'focus_safe'


@dataclass(frozen=True, slots=True)
class WorkspaceDeepLink:
    workspace: WorkspaceId
    section: str | None = None

    def as_uri(self) -> str:
        if self.section is None:
            return f'htdt://workspace/{self.workspace.value}'
        return f'htdt://workspace/{self.workspace.value}/{self.section}'


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    command_id: str
    display_name: str
    contexts: frozenset[CommandContext] = field(
        default_factory=lambda: frozenset({CommandContext.GLOBAL})
    )
    shortcut: str | None = None
    shortcut_aliases: tuple[str, ...] = ()
    shortcut_behavior: ShortcutBehavior = ShortcutBehavior.FOCUS_SAFE
    keywords: tuple[str, ...] = ()
    deep_link: WorkspaceDeepLink | None = None

    def __post_init__(self) -> None:
        if not self.command_id or self.command_id.strip() != self.command_id:
            raise ValueError('command_id must be non-empty and trimmed')
        if not self.display_name.strip():
            raise ValueError('display_name must be non-empty')
        if not self.contexts:
            raise ValueError('contexts must not be empty')


@dataclass(frozen=True, slots=True)
class CommandAvailability:
    enabled: bool
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        if self.enabled and self.disabled_reason:
            raise ValueError('enabled command cannot have disabled_reason')
        if not self.enabled and not self.disabled_reason:
            raise ValueError('disabled command requires disabled_reason')

    @classmethod
    def available(cls) -> 'CommandAvailability':
        return cls(enabled=True)

    @classmethod
    def unavailable(cls, reason: str) -> 'CommandAvailability':
        return cls(enabled=False, disabled_reason=reason)


@dataclass(frozen=True, slots=True)
class CommandSearchResult:
    definition: CommandDefinition
    availability: CommandAvailability
    score: int


AvailabilityProvider = Callable[[], CommandAvailability]
CommandExecutor = Callable[[], None]
DeepLinkHandler = Callable[[WorkspaceDeepLink], None]


@dataclass(slots=True)
class _RegisteredCommand:
    definition: CommandDefinition
    execute: CommandExecutor | None
    availability: AvailabilityProvider | None
    order: int


def _normalized(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold().strip()


def command_shortcut_allowed(
    definition: CommandDefinition,
    *,
    text_input_focused: bool,
) -> bool:
    if not text_input_focused:
        return True
    return definition.shortcut_behavior == ShortcutBehavior.GLOBAL


class CommandRegistry:
    def __init__(self, *, deep_link_handler: DeepLinkHandler | None = None) -> None:
        self._commands: dict[str, _RegisteredCommand] = {}
        self._deep_link_handler = deep_link_handler

    def set_deep_link_handler(self, handler: DeepLinkHandler | None) -> None:
        self._deep_link_handler = handler

    def register(
        self,
        definition: CommandDefinition,
        *,
        execute: CommandExecutor | None = None,
        availability: AvailabilityProvider | None = None,
    ) -> None:
        if definition.command_id in self._commands:
            raise ValueError(f'duplicate command id: {definition.command_id}')
        if execute is None and definition.deep_link is None:
            raise ValueError(
                f'command {definition.command_id} needs an executor or a workspace deep-link'
            )
        self._commands[definition.command_id] = _RegisteredCommand(
            definition=definition,
            execute=execute,
            availability=availability,
            order=len(self._commands),
        )

    def definition(self, command_id: str) -> CommandDefinition:
        return self._commands[command_id].definition

    def definitions(self) -> tuple[CommandDefinition, ...]:
        return tuple(item.definition for item in self._commands.values())

    def availability(self, command_id: str) -> CommandAvailability:
        command = self._commands[command_id]
        if command.availability is not None:
            result = command.availability()
            if not result.enabled:
                return result
        if command.execute is None and command.definition.deep_link is not None:
            if self._deep_link_handler is None:
                return CommandAvailability.unavailable(
                    'ワークスペース切替は新しいシェルのrouter接続後に利用できます'
                )
        return CommandAvailability.available()

    def execute(self, command_id: str) -> bool:
        command = self._commands[command_id]
        availability = self.availability(command_id)
        if not availability.enabled:
            return False
        if command.execute is not None:
            command.execute()
            return True
        deep_link = command.definition.deep_link
        if deep_link is None or self._deep_link_handler is None:
            return False
        self._deep_link_handler(deep_link)
        return True

    def search(
        self,
        query: str = '',
        *,
        context: CommandContext | None = None,
    ) -> tuple[CommandSearchResult, ...]:
        normalized_query = _normalized(query)
        tokens = tuple(token for token in normalized_query.split() if token)
        matches: list[CommandSearchResult] = []
        for command in self._commands.values():
            definition = command.definition
            score = self._score(definition, normalized_query, tokens, context)
            if score is None:
                continue
            matches.append(
                CommandSearchResult(
                    definition=definition,
                    availability=self.availability(definition.command_id),
                    score=score,
                )
            )
        matches.sort(
            key=lambda item: (
                not item.availability.enabled,
                -item.score,
                self._commands[item.definition.command_id].order,
            )
        )
        return tuple(matches)

    @staticmethod
    def _score(
        definition: CommandDefinition,
        query: str,
        tokens: tuple[str, ...],
        context: CommandContext | None,
    ) -> int | None:
        haystacks = (
            _normalized(definition.display_name),
            _normalized(definition.command_id),
            *(_normalized(keyword) for keyword in definition.keywords),
            *(_normalized(shortcut) for shortcut in (
                (definition.shortcut,) + definition.shortcut_aliases
                if definition.shortcut is not None
                else definition.shortcut_aliases
            )),
        )
        if tokens and not all(any(token in value for value in haystacks) for token in tokens):
            return None

        score = 10
        if context is not None and context in definition.contexts:
            score += 20
        if not query:
            return score

        display = haystacks[0]
        command_id = haystacks[1]
        keyword_values = haystacks[2:2 + len(definition.keywords)]
        if query == display:
            score += 100
        elif display.startswith(query):
            score += 85
        elif query in display:
            score += 70

        if query == command_id:
            score += 65
        elif command_id.startswith(query):
            score += 50
        elif query in command_id:
            score += 35

        for keyword in keyword_values:
            if query == keyword:
                score += 55
            elif keyword.startswith(query):
                score += 40
            elif query in keyword:
                score += 25
        return score


def default_command_definitions() -> tuple[CommandDefinition, ...]:
    return (
        CommandDefinition(
            command_id='navigation.overview',
            display_name='概要',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.OVERVIEW}),
            keywords=('overview', 'ホーム', 'ダッシュボード'),
            deep_link=WorkspaceDeepLink(WorkspaceId.OVERVIEW),
            shortcut_behavior=ShortcutBehavior.GLOBAL,
        ),
        CommandDefinition(
            command_id='navigation.room',
            display_name='部屋',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.ROOM}),
            keywords=('room', '3D', 'CAD'),
            deep_link=WorkspaceDeepLink(WorkspaceId.ROOM),
            shortcut_behavior=ShortcutBehavior.GLOBAL,
        ),
        CommandDefinition(
            command_id='navigation.measurements',
            display_name='測定',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.MEASUREMENTS}),
            keywords=('measurement', 'REW', '実測'),
            deep_link=WorkspaceDeepLink(WorkspaceId.MEASUREMENTS),
            shortcut_behavior=ShortcutBehavior.GLOBAL,
        ),
        CommandDefinition(
            command_id='navigation.optimization',
            display_name='最適化',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.OPTIMIZATION}),
            keywords=('optimize', 'optimization', '候補'),
            deep_link=WorkspaceDeepLink(WorkspaceId.OPTIMIZATION),
            shortcut_behavior=ShortcutBehavior.GLOBAL,
        ),
        CommandDefinition(
            command_id='project.save',
            display_name='保存',
            contexts=frozenset({CommandContext.GLOBAL}),
            shortcut='Ctrl+S',
            shortcut_behavior=ShortcutBehavior.GLOBAL,
            keywords=('save', '保存する'),
        ),
        CommandDefinition(
            command_id='edit.undo',
            display_name='元に戻す',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.ROOM}),
            shortcut='Ctrl+Z',
            shortcut_behavior=ShortcutBehavior.FOCUS_SAFE,
            keywords=('undo',),
        ),
        CommandDefinition(
            command_id='edit.redo',
            display_name='やり直す',
            contexts=frozenset({CommandContext.GLOBAL, CommandContext.ROOM}),
            shortcut='Ctrl+Y',
            shortcut_aliases=('Ctrl+Shift+Z',),
            shortcut_behavior=ShortcutBehavior.FOCUS_SAFE,
            keywords=('redo',),
        ),
        CommandDefinition(
            command_id='room.draw',
            display_name='部屋作図',
            contexts=frozenset({CommandContext.ROOM}),
            keywords=('部屋を作図', 'draw room', 'room geometry', '形状'),
            deep_link=WorkspaceDeepLink(WorkspaceId.ROOM, 'geometry'),
        ),
        CommandDefinition(
            command_id='room.add_speaker',
            display_name='スピーカー追加',
            contexts=frozenset({CommandContext.ROOM}),
            keywords=('スピーカーを追加', 'add speaker', 'speaker'),
            deep_link=WorkspaceDeepLink(WorkspaceId.ROOM, 'speakers'),
        ),
        CommandDefinition(
            command_id='measurements.import_rew',
            display_name='REW読み込み',
            contexts=frozenset({CommandContext.MEASUREMENTS}),
            keywords=('REWを読み込む', 'import REW', '測定取込', '測定読み込み'),
            deep_link=WorkspaceDeepLink(WorkspaceId.MEASUREMENTS, 'import'),
        ),
        CommandDefinition(
            command_id='prediction.run',
            display_name='予測実行',
            contexts=frozenset({CommandContext.ROOM}),
            keywords=('予測を実行', 'run prediction', 'acoustics', '音響'),
            deep_link=WorkspaceDeepLink(WorkspaceId.ROOM, 'acoustics'),
        ),
        CommandDefinition(
            command_id='optimization.compare_candidates',
            display_name='候補比較',
            contexts=frozenset({CommandContext.OPTIMIZATION}),
            keywords=('候補を比較', 'candidate compare', 'Pareto', 'パレート'),
            deep_link=WorkspaceDeepLink(WorkspaceId.OPTIMIZATION, 'candidates'),
        ),
    )


def register_default_commands(
    registry: CommandRegistry,
    *,
    bindings: dict[
        str,
        tuple[CommandExecutor | None, AvailabilityProvider | None],
    ] | None = None,
) -> None:
    bindings = bindings or {}
    for definition in default_command_definitions():
        execute, availability = bindings.get(definition.command_id, (None, None))
        registry.register(
            definition,
            execute=execute,
            availability=availability,
        )

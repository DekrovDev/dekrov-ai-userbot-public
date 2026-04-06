from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from chat.chat_config import ChatConfigStore
from chat.chat_topics import ChatTopicStore
from config.settings import load_config
from app.control_bot import ControlBotService
from app.chat_bot import ChatBotService
from infra.container import Container
from infra.scheduler import SchedulerStore
from chat.monitor import MonitorStore
from memory.entity_memory import EntityMemoryStore
from ai.groq_client import GroqClient
from live.live_cache import LiveCacheStore
from live.live_router import LiveDataRouter
from ai.model_stats import ModelStatsStore
from memory.owner_knowledge import OwnerKnowledgeStore
from memory.owner_directives import OwnerDirectiveStore
from memory.shared_memory import SharedMemoryStore
from state.state import StateStore
from memory.style_profile import StyleProfileStore
from memory.user_memory import UserMemoryStore
from app.userbot_core import UserbotService
from visitor.visitor_service import VisitorService

LOGGER = logging.getLogger("assistant.main")


def _load_env_file(env_path: Path) -> None:
    """Load .env file into process environment.

    Only sets variables not already defined (os.environ.setdefault).
    This allows environment variables to override .env file.

    Args:
        env_path: Path to .env file
    """
    if not env_path.exists():
        return
    try:
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            os.environ.setdefault(key, value)
    except OSError:
        pass


def configure_logging(json_format: bool = True) -> None:
    """ÐÐ°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ.

    Args:
        json_format: Ð•ÑÐ»Ð¸ True, Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÑŒ JSON-Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚
    """
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "assistant.log"

    if json_format:
        from infra.json_logger import JsonFormatter

        formatter = JsonFormatter(include_extra=True, include_location=False)
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        force=True,
    )


def configure_asyncio_logging() -> None:
    loop = asyncio.get_running_loop()

    def handle_asyncio_exception(_: asyncio.AbstractEventLoop, context: dict) -> None:
        exception = context.get("exception")
        message = context.get("message", "Unhandled asyncio exception")
        logging.getLogger("asyncio").error(message, exc_info=exception)

    loop.set_exception_handler(handle_asyncio_exception)


def log_runtime_notes() -> None:
    if importlib.util.find_spec("tgcrypto") is None:
        logging.getLogger("assistant.main").warning(
            "tgcrypto_not_installed performance=degraded hint='Install tgcrypto on Python <= 3.13 or with MSVC Build Tools'"
        )


async def run() -> None:
    _load_env_file(Path(__file__).parent / ".env")
    configure_logging()
    configure_asyncio_logging()
    log_runtime_notes()
    config = load_config()
    LOGGER.info(
        "config_loaded live_data_enabled=%s reject_live_data_requests=%s strict_outgoing_only=%s allow_incoming_trigger_commands=%s default_active_model=%s default_judge_model=%s default_triggers=%s response_style=%s",
        config.live_data_enabled,
        config.reject_live_data_requests,
        config.strict_outgoing_only,
        config.allow_incoming_trigger_commands,
        config.default_active_model,
        config.default_judge_model,
        ",".join(config.default_trigger_aliases),
        config.default_response_style_mode,
    )


    container = Container()


    # Config
    container.register_singleton("config", lambda _: config)

    # StateStore
    container.register_singleton(
        StateStore,
        lambda c: StateStore(
            c.resolve("config").state_path,
            c.resolve("config").default_models,
            c.resolve("config").default_active_model,
            c.resolve("config").default_judge_model,
            c.resolve("config").default_enabled_models,
            c.resolve("config").default_trigger_aliases,
            c.resolve("config").default_dot_prefix_required,
            c.resolve("config").default_command_mode_enabled,
            c.resolve("config").default_auto_reply_enabled,
            c.resolve("config").default_fallback_enabled,
            db_path=c.resolve("config").base_dir / "data" / "state.db",
        ),
    )

    # StyleProfileStore
    container.register_singleton(
        StyleProfileStore,
        lambda c: StyleProfileStore(
            c.resolve("config").style_profile_path, config=c.resolve("config")
        ),
    )

    # ChatTopicStore
    container.register_singleton(
        ChatTopicStore,
        lambda c: ChatTopicStore(
            c.resolve("config").chat_topics_path,
            c.resolve("config").owner_reference_aliases,
        ),
    )

    # ChatConfigStore
    container.register_singleton(
        ChatConfigStore, lambda c: ChatConfigStore(c.resolve("config").chat_config_path)
    )

    # UserMemoryStore
    container.register_singleton(
        UserMemoryStore,
        lambda c: UserMemoryStore(c.resolve("config").user_profiles_path),
    )

    # SharedMemoryStore
    container.register_singleton(
        SharedMemoryStore,
        lambda c: SharedMemoryStore(c.resolve("config").shared_memory_path),
    )

    # OwnerDirectiveStore
    container.register_singleton(
        OwnerDirectiveStore,
        lambda c: OwnerDirectiveStore(c.resolve("config").owner_directives_path),
    )

    # EntityMemoryStore
    container.register_singleton(
        EntityMemoryStore,
        lambda c: EntityMemoryStore(c.resolve("config").entity_memory_path),
    )

    # OwnerKnowledgeStore
    container.register_singleton(
        OwnerKnowledgeStore,
        lambda c: OwnerKnowledgeStore(c.resolve("config").owner_knowledge_path),
    )

    # ModelStatsStore
    container.register_singleton(
        ModelStatsStore, lambda c: ModelStatsStore(c.resolve("config").model_stats_path)
    )

    # LiveCacheStore
    container.register_singleton(
        LiveCacheStore, lambda c: LiveCacheStore(c.resolve("config").live_cache_path)
    )

    # SchedulerStore
    container.register_singleton(
        SchedulerStore, lambda c: SchedulerStore(c.resolve("config").scheduler_path)
    )

    # MonitorStore
    container.register_singleton(
        MonitorStore, lambda c: MonitorStore(c.resolve("config").monitor_path)
    )

    # GroqClient
    container.register_singleton(
        GroqClient,
        lambda c: GroqClient(
            c.resolve("config"), c.resolve(StateStore), c.resolve(ModelStatsStore)
        ),
    )

    # LiveDataRouter
    container.register_singleton(
        LiveDataRouter,
        lambda c: LiveDataRouter(c.resolve("config"), c.resolve(LiveCacheStore)),
    )

    # VisitorService
    container.register_singleton(
        VisitorService,
        lambda c: VisitorService(
            c.resolve("config"), c.resolve(GroqClient), c.resolve(OwnerKnowledgeStore)
        ),
    )

    # UserbotService
    container.register_singleton(
        UserbotService,
        lambda c: UserbotService(
            c.resolve("config"),
            c.resolve(StateStore),
            c.resolve(GroqClient),
            c.resolve(StyleProfileStore),
            c.resolve(ChatTopicStore),
            c.resolve(ChatConfigStore),
            c.resolve(LiveDataRouter),
            c.resolve(UserMemoryStore),
            c.resolve(SharedMemoryStore),
            c.resolve(OwnerDirectiveStore),
            c.resolve(EntityMemoryStore),
            c.resolve(OwnerKnowledgeStore),
            scheduler_store=c.resolve(SchedulerStore),
            monitor_store=c.resolve(MonitorStore),
        ),
    )

    # ControlBotService
    container.register_singleton(
        ControlBotService,
        lambda c: ControlBotService(
            c.resolve("config"),
            c.resolve(StateStore),
            c.resolve(GroqClient),
            c.resolve(StyleProfileStore),
            c.resolve(UserMemoryStore),
            c.resolve(EntityMemoryStore),
            c.resolve(OwnerDirectiveStore),
        ),
    )

    # ChatBotService (ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ñ‚Ð¾ÐºÐµÐ½)
    if config.chat_bot_token:
        container.register_singleton(
            ChatBotService,
            lambda c: ChatBotService(
                c.resolve("config"),
                c.resolve(StateStore),
                c.resolve(GroqClient),
                c.resolve(OwnerKnowledgeStore),
                c.resolve(LiveDataRouter),
                c.resolve(VisitorService),
            ),
        )


    container.initialize()


    state = container.resolve(StateStore)
    snapshot = await state.load()
    if set(snapshot.available_models) != set(config.default_models):
        snapshot = await state.sync_model_pool(config.default_models)
    if snapshot.trigger_aliases != config.default_trigger_aliases:
        await state.set_trigger_aliases(config.default_trigger_aliases)
    if snapshot.dot_prefix_required != config.default_dot_prefix_required:
        await state.set_dot_prefix_required(config.default_dot_prefix_required)
    if snapshot.command_mode_enabled != config.default_command_mode_enabled:
        await state.set_command_mode_enabled(config.default_command_mode_enabled)
    if config.strict_outgoing_only:
        LOGGER.info(
            "strict_outgoing_only_limits_owner_command_messages=%s incoming_trigger_commands_enabled=%s auto_reply_configured=%s",
            not config.allow_incoming_trigger_commands,
            config.allow_incoming_trigger_commands,
            snapshot.auto_reply_enabled,
        )

    await container.load_all()

    # Startup cleanup â€” remove stale profiles on boot
    try:
        entity_memory_store = container.resolve(EntityMemoryStore)
        user_memory_store = container.resolve(UserMemoryStore)
        removed_em = await entity_memory_store.cleanup_stale_entries(max_age_days=30)
        removed_um = await user_memory_store.cleanup_stale_profiles(
            max_age_days=30, min_messages=5
        )
        if removed_em or removed_um:
            LOGGER.info("startup_cleanup entity=%d profiles=%d", removed_em, removed_um)
    except Exception:
        LOGGER.debug("startup_cleanup_failed", exc_info=True)

    if snapshot.response_style_mode != config.default_response_style_mode:
        snapshot = await state.set_response_style_mode(
            config.default_response_style_mode
        )


    userbot = container.resolve(UserbotService)
    control_bot: ControlBotService | None = None
    chat_bot: ChatBotService | None = None

    try:
        await userbot.start()
        if config.owner_user_id <= 0:
            config.owner_user_id = userbot.user_id
        visitor_service = container.resolve(VisitorService)
        visitor_service.set_public_channel_reader(
            userbot.build_visitor_public_channel_context
        )

        control_bot = container.resolve(ControlBotService)
        await control_bot.start()

        if config.chat_bot_token:
            chat_bot = container.resolve(ChatBotService)
            await chat_bot.start()

            # Wire draft callback and scheduler
            chat_bot.set_draft_callback(userbot.draft_callback_for_chat_bot)
            scheduler_store = container.resolve(SchedulerStore)
            scheduler_store.set_fire_callback(userbot.fire_scheduled_task)
            await scheduler_store.start_all()

            # Daily entity memory cleanup
            async def _daily_memory_cleanup():
                import asyncio as _asyncio

                while True:
                    try:
                        removed = await entity_memory_store.cleanup_stale_entries(
                            max_age_days=30
                        )
                        if removed:
                            LOGGER.info("entity_memory_cleanup removed=%d", removed)
                        removed_profiles = (
                            await user_memory_store.cleanup_stale_profiles(
                                max_age_days=30, min_messages=5
                            )
                        )
                        if removed_profiles:
                            LOGGER.info(
                                "user_memory_cleanup removed=%d", removed_profiles
                            )
                    except Exception:
                        pass
                    await _asyncio.sleep(86400)

            asyncio.create_task(_daily_memory_cleanup())

            # Visitor session cleanup
            async def _visitor_cleanup():
                import asyncio as _asyncio

                while True:
                    try:
                        visitor_service = container.resolve(VisitorService)
                        ended = await visitor_service.cleanup_inactive_sessions()
                        if ended:
                            logging.getLogger("assistant.visitor").info(
                                "auto_ended_inactive_sessions count=%d", ended
                            )
                    except Exception:
                        pass
                    await _asyncio.sleep(120)

            asyncio.create_task(_visitor_cleanup())
        else:
            LOGGER.info("chat_bot_skipped no CHAT_BOT_TOKEN")

        try:
            groq_client = container.resolve(GroqClient)
            await groq_client.refresh_models()
        except Exception:
            LOGGER.exception("startup_model_refresh_failed")

        await asyncio.Event().wait()
    finally:
        if chat_bot is not None:
            await chat_bot.stop()
        if control_bot is not None:
            await control_bot.stop()
        await userbot.stop()
        scheduler_store = container.get_service(SchedulerStore)
        if scheduler_store:
            await scheduler_store.cancel_all()
        live_router = container.get_service(LiveDataRouter)
        if live_router:
            await live_router.close()
        groq_client = container.get_service(GroqClient)
        if groq_client:
            await groq_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


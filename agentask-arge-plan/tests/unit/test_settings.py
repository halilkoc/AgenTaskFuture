"""T17/T18 ve docs/05_CONFIGURATION.md kuralları."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.config import AppEnv, ConfigurationError, Settings, load_settings
from tests.conftest import SETTING_KEYS, TEST_SIGNING_KEY, EnvFileFactory, parse_env_example

PROD_BASE = {
    "APP_ENV": "production",
    "AUTH_MODE": "dev",
    "DEV_AUTH_ENABLED": "false",
}


def _problems(exc: pytest.ExceptionInfo[ConfigurationError]) -> str:
    return "\n".join(exc.value.problems)


# ---- .env.example ile Settings tek kaynak ------------------------------------


def test_env_example_documents_exactly_the_settings_fields() -> None:
    # LOCAL_MONGO_ (AUTOSTART hariç) yerel geliştirme aracına ayrılmıştır; araç paritesi ayrı testte
    # (tests/unit/test_local_mongo_tool.py::test_env_example_documents_exactly_the_tool_fields) doğrulanır.
    app_keys = [
        k for k in parse_env_example() if not k.startswith("LOCAL_MONGO_") or k == "LOCAL_MONGO_AUTOSTART"
    ]
    assert sorted(app_keys) == SETTING_KEYS


def test_env_example_loads_once_signing_key_is_provided(
    make_env_file: EnvFileFactory,
) -> None:
    settings = load_settings(make_env_file())
    assert settings.app_env is AppEnv.DEVELOPMENT
    assert settings.target_allowed_origins == ["http://127.0.0.1:8100", "http://127.0.0.1:8101"]
    # Boş opsiyonel path'ler None olur (override edilmez).
    assert settings.browser_executable_path is None
    assert settings.playwright_browsers_path is None
    assert settings.llm_api_key is None


def test_raw_env_example_is_rejected_because_signing_key_is_empty() -> None:
    from tests.conftest import ENV_EXAMPLE

    with pytest.raises(ConfigurationError) as exc:
        load_settings(ENV_EXAMPLE)
    assert "SESSION_SIGNING_KEY" in _problems(exc)


def test_required_setting_missing_is_explicit_error(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(RUN_MAX_STEPS=None))
    assert "RUN_MAX_STEPS: zorunlu ayar eksik veya boş" in _problems(exc)


# ---- tipler ------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["false", "False", "FALSE", "0"])
def test_false_booleans_are_really_false(make_env_file: EnvFileFactory, raw: str) -> None:
    settings = load_settings(make_env_file(BROWSER_HEADLESS=raw, EVIDENCE_SCREENSHOTS_ENABLED=raw))
    assert settings.browser_headless is False
    assert settings.evidence_screenshots_enabled is False


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("BROWSER_HEADLESS", "maybe", "true/false"),
        ("RUN_MAX_STEPS", "abc", "tam sayı"),
        ("RUN_MAX_STEPS", "0", "pozitif"),
        ("FRAME_SCAN_MAX_ELEMENTS", "-5", "pozitif"),
        ("APP_PORT", "70000", "üst sınır"),
        ("APP_ENV", "staging", "APP_ENV"),
        ("BROWSER_ENGINE", "edge", "BROWSER_ENGINE"),
        ("APP_TIMEZONE", "Mars/Olympus", "saat dilimi"),
        ("TARGET_ALLOWED_ORIGINS", '["http://127.0.0.1:8100/path"]', "origin"),
        ("TARGET_BASE_URL", "http://127.0.0.1:9999", "TARGET_ALLOWED_ORIGINS"),
        ("MONGO_URI", "postgres://x", "mongodb://"),
        ("SESSION_SIGNING_KEY", "short", "en az 32"),
    ],
)
def test_invalid_values_are_rejected_not_defaulted(
    make_env_file: EnvFileFactory, key: str, value: str, fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{key: value}))
    assert fragment in _problems(exc)


# ---- öncelik ve dosya seçimi (T18) -------------------------------------------


def test_process_environment_overrides_dotenv(
    make_env_file: EnvFileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = make_env_file(RUN_MAX_STEPS="100", BROWSER_HEADLESS="false")
    monkeypatch.setenv("RUN_MAX_STEPS", "7")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    settings = load_settings(env_file)
    assert settings.run_max_steps == 7
    assert settings.browser_headless is True


def test_invalid_process_env_is_not_masked_by_valid_dotenv(
    make_env_file: EnvFileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUN_MAX_STEPS", "-1")
    with pytest.raises(ConfigurationError):
        load_settings(make_env_file())


def test_default_env_file_is_dotenv_in_working_directory(
    make_env_file: EnvFileFactory, tmp_path: Path
) -> None:
    make_env_file(name=".env", RUN_MAX_STEPS="42")
    assert load_settings().run_max_steps == 42


def test_explicit_env_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(tmp_path / "missing.env")
    assert "bulunamadı" in _problems(exc)


def test_process_environment_alone_is_sufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    values = parse_env_example()
    values["SESSION_SIGNING_KEY"] = TEST_SIGNING_KEY
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert load_settings(use_default_env_file=False).app_port == 8000


def test_unknown_key_in_dotenv_is_rejected(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(RUN_MAX_STEP="5"))
    assert "RUN_MAX_STEP: bilinmeyen ayar" in _problems(exc)


def test_unrelated_process_env_is_ignored(
    make_env_file: EnvFileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOME_OTHER_TOOL_SETTING", "x")
    load_settings(make_env_file())


# ---- secret redaksiyonu (T17) ------------------------------------------------


def test_secrets_are_masked_in_repr_and_dump(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(MONGO_URI="mongodb://admin:hunter2-mongo@127.0.0.1:27017", LLM_API_KEY="sk-live-zzz")
    )
    text = repr(settings) + str(settings.model_dump())
    for secret in (TEST_SIGNING_KEY, "hunter2-mongo", "sk-live-zzz"):
        assert secret not in text


def test_validation_errors_never_echo_input_values(make_env_file: EnvFileFactory) -> None:
    secret = "sk-very-secret-value-should-not-leak"
    with pytest.raises(ConfigurationError) as exc:
        load_settings(
            make_env_file(
                SESSION_SIGNING_KEY=secret[:10],
                MONGO_URI=f"postgres://{secret}",
                LLM_API_KEY=secret,
                LLM_PASWORD=secret,  # yazım hatalı anahtar: değeri yine sızmamalı
                RUN_MAX_STEPS=secret,
            )
        )
    rendered = str(exc.value) + repr(exc.value) + repr(exc.value.__cause__) + repr(exc.value.__context__)
    assert secret not in rendered
    assert secret[:10] not in rendered


# ---- koşullu kurallar --------------------------------------------------------


def test_llm_disabled_does_not_require_credentials(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(LLM_ENABLED="false", LLM_BASE_URL="", LLM_MODEL=""))
    assert settings.llm_enabled is False


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"LLM_MODEL": "m"}, "LLM_BASE_URL zorunlu"),
        ({"LLM_BASE_URL": "http://127.0.0.1:9000/v1"}, "LLM_MODEL zorunlu"),
        (
            {"LLM_BASE_URL": "http://127.0.0.1:9000/v1", "LLM_MODEL": "m", "LLM_AUTH_MODE": "bearer"},
            "LLM_API_KEY zorunlu",
        ),
        (
            {
                "LLM_BASE_URL": "http://127.0.0.1:9000/v1",
                "LLM_MODEL": "m",
                "LLM_AUTH_MODE": "basic",
                "LLM_USERNAME": "u",
            },
            "LLM_PASSWORD zorunlu",
        ),
        (
            {
                "LLM_BASE_URL": "http://127.0.0.1:9000/v1",
                "LLM_MODEL": "m",
                "LLM_CONTEXT_TOKENS": "8192",
                "LLM_MAX_INPUT_TOKENS": "6000",
                "LLM_MAX_OUTPUT_TOKENS": "2048",
                "LLM_CONTEXT_RESERVE_TOKENS": "1024",
            },
            "aşamaz",
        ),
    ],
)
def test_llm_enabled_requires_complete_config(
    make_env_file: EnvFileFactory, overrides: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(LLM_ENABLED="true", **overrides))
    assert fragment in _problems(exc)


def test_llm_enabled_with_complete_config_loads(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(
            LLM_ENABLED="true",
            LLM_BASE_URL="http://127.0.0.1:9000/v1",
            LLM_MODEL="local-model",
            LLM_AUTH_MODE="bearer",
            LLM_API_KEY="k",
        )
    )
    assert settings.llm_enabled and settings.llm_model == "local-model"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"AUTH_MODE": "dev"}, "AUTH_MODE=dev yalnızca APP_ENV=development"),
        ({"AUTH_MODE": "unconfigured", "DEV_AUTH_ENABLED": "true"}, "DEV_AUTH_ENABLED=true kabul edilmez"),
        ({"AUTH_MODE": "unconfigured"}, "AUTH_MODE=unconfigured hazır kimlik değildir"),
        ({"AUTH_MODE": "unconfigured", "LLM_TLS_VERIFY": "false"}, "LLM_TLS_VERIFY=false"),
        (
            {
                "AUTH_MODE": "unconfigured",
                "LLM_ENABLED": "true",
                "LLM_BASE_URL": "http://llm.internal/v1",
                "LLM_MODEL": "m",
                "LLM_AUTH_MODE": "bearer",
                "LLM_API_KEY": "k",
            },
            "http üzerinden",
        ),
    ],
)
def test_production_rejects_unsafe_modes(
    make_env_file: EnvFileFactory, overrides: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{**PROD_BASE, **overrides}))
    assert fragment in _problems(exc)


def test_dev_auth_requires_explicit_enable(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(DEV_AUTH_ENABLED="false"))
    assert "DEV_AUTH_ENABLED=true açıkça" in _problems(exc)


def test_dev_auth_requires_loopback_binding(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(APP_HOST="0.0.0.0"))  # noqa: S104
    assert "loopback" in _problems(exc)


def test_tls_verify_false_allowed_only_explicitly_in_development(make_env_file: EnvFileFactory) -> None:
    assert load_settings(make_env_file(LLM_TLS_VERIFY="false")).llm_tls_verify is False
    with pytest.raises(ConfigurationError):
        load_settings(make_env_file(APP_ENV="test", AUTH_MODE="unconfigured", LLM_TLS_VERIFY="false"))


def test_settings_are_immutable(make_env_file: EnvFileFactory) -> None:
    settings: Settings = load_settings(make_env_file())
    with pytest.raises(Exception):  # noqa: B017
        settings.run_max_steps = 1  # type: ignore[misc]


# ---- P1: lab ve browser oturum ayarları ---------------------------------------


def test_p1_settings_load_from_env_example(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file())
    assert settings.lab_primary_origin == "http://127.0.0.1:8100"
    assert settings.lab_secondary_origin == "http://127.0.0.1:8101"
    assert settings.browser_max_sessions >= settings.browser_max_sessions_per_user >= 1
    assert settings.navigation_timeout_ms > 0


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"LAB_PRIMARY_ORIGIN": "http://10.0.0.1:8100"}, "loopback"),
        ({"LAB_SECONDARY_ORIGIN": "https://127.0.0.1:8101"}, "http"),
        ({"LAB_SECONDARY_ORIGIN": "http://127.0.0.1:8100"}, "farklı"),
        ({"LAB_SECONDARY_ORIGIN": None}, "birlikte"),
        (
            {"BROWSER_MAX_SESSIONS": "1", "BROWSER_MAX_SESSIONS_PER_USER": "2"},
            "BROWSER_MAX_SESSIONS_PER_USER",
        ),
        ({"BROWSER_SESSION_IDLE_SECONDS": "0"}, "pozitif"),
    ],
)
def test_p1_invalid_settings_rejected(
    make_env_file: EnvFileFactory, overrides: dict[str, str | None], fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**overrides))
    assert fragment in _problems(exc)


def test_lab_origins_rejected_in_production(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{**PROD_BASE, "AUTH_MODE": "unconfigured"}))
    assert "LAB_" in _problems(exc)


def test_lab_origins_optional(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(LAB_PRIMARY_ORIGIN=None, LAB_SECONDARY_ORIGIN=None))
    assert settings.lab_primary_origin is None and settings.lab_secondary_origin is None


# ---- P2: gözlem bütçeleri ----------------------------------------------------


def test_p2_observation_settings_load(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file())
    assert settings.observe_timeout_ms >= settings.frame_scan_timeout_ms
    assert settings.observe_max_frames >= 1
    assert settings.picker_wait_max_ms >= 1


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"OBSERVE_MAX_FRAMES": "0"}, "pozitif"),
        ({"OBSERVE_TIMEOUT_MS": "100", "FRAME_SCAN_TIMEOUT_MS": "5000"}, "OBSERVE_TIMEOUT_MS"),
        ({"PICKER_WAIT_MAX_MS": "-1"}, "pozitif"),
    ],
)
def test_p2_invalid_observation_settings(
    make_env_file: EnvFileFactory, overrides: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**overrides))
    assert fragment in _problems(exc)


# ---- P3: yürütme ayarları ------------------------------------------------------


def test_p3_execution_settings_load(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file())
    assert settings.run_directory.name == "runs"
    assert settings.approved_action_set.value == "lab"
    assert settings.outcome_timeout_ms > 0 and settings.reconcile_timeout_ms > 0
    assert settings.table_no_progress_limit >= 1


def test_lab_action_set_rejected_in_production(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(
            make_env_file(
                **{
                    **PROD_BASE,
                    "AUTH_MODE": "unconfigured",
                    "LAB_PRIMARY_ORIGIN": None,
                    "LAB_SECONDARY_ORIGIN": None,
                }
            )
        )
    assert "APPROVED_ACTION_SET=lab" in _problems(exc)


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("APPROVED_ACTION_SET", "anything", "APPROVED_ACTION_SET"),
        ("OUTCOME_TIMEOUT_MS", "0", "pozitif"),
        ("TABLE_NO_PROGRESS_LIMIT", "0", "pozitif"),
    ],
)
def test_p3_invalid_settings(make_env_file: EnvFileFactory, key: str, value: str, fragment: str) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{key: value}))
    assert fragment in _problems(exc)


# ---- P5: katalog yayın ayarları --------------------------------------------------


def test_p5_catalog_settings(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file())
    assert settings.catalog_backend.value == "mongo"
    assert settings.catalog_environment == "arge"
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(CATALOG_ENVIRONMENT="Arge Ortamı"))
    assert "CATALOG_ENVIRONMENT" in _problems(exc)
    assert load_settings(make_env_file(CATALOG_BACKEND="disabled")).catalog_backend.value == "disabled"


# ---- Yerel Mongo otomatik başlatma bayrağı --------------------------------------


def test_local_mongo_autostart_flag(make_env_file: EnvFileFactory) -> None:
    assert load_settings(make_env_file()).local_mongo_autostart is False
    assert load_settings(make_env_file(LOCAL_MONGO_AUTOSTART="true")).local_mongo_autostart is True
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(LOCAL_MONGO_AUTOSTART="belki"))
    assert "LOCAL_MONGO_AUTOSTART" in _problems(exc)


@pytest.mark.parametrize("env", ["test", "production"])
def test_local_mongo_autostart_only_in_development(make_env_file: EnvFileFactory, env: str) -> None:
    overrides = {
        "APP_ENV": env,
        "AUTH_MODE": "unconfigured",
        "DEV_AUTH_ENABLED": "false",
        "LOCAL_MONGO_AUTOSTART": "true",
    }
    if env == "production":
        overrides.update(LAB_PRIMARY_ORIGIN=None, LAB_SECONDARY_ORIGIN=None, APPROVED_ACTION_SET="none")
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**overrides))
    assert "LOCAL_MONGO_AUTOSTART=true yalnız APP_ENV=development" in _problems(exc)


def test_tool_prefixed_keys_tolerated_but_other_unknown_keys_rejected(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(LOCAL_MONGO_PORT="27999", LOCAL_MONGO_WHATEVER="x"))
    assert not hasattr(settings, "local_mongo_port")  # uygulama araç ayarlarını bilmez
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(LOCAL_MONGOPORT="1"))
    assert "LOCAL_MONGOPORT: bilinmeyen ayar" in _problems(exc)


# ---- AUTOMATION_APPLICATIONS_JSON -------------------------------------------


def test_env_example_has_no_duplicate_active_keys() -> None:
    from tests.conftest import env_example_active_keys

    keys = env_example_active_keys()
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    assert duplicates == [], f"yinelenen anahtar (son tanım öncekini sessizce ezer): {duplicates}"


def test_env_example_single_lab_application_is_valid(make_env_file: EnvFileFactory) -> None:
    # Örnek dosyanın kendisi doğrulanır (tek uygulamalı yerel lab). Çok uygulamalı davranış testleri uygulama
    # listesini açıkça verir; örnekteki uygulama sayısına bağlı değildir.
    settings = load_settings(make_env_file())
    apps = settings.automation_applications_json
    assert [(a.id, a.origin) for a in apps] == [("lab", "http://127.0.0.1:8100")]
    assert settings.catalog_application_id in {a.id for a in apps}


def test_two_configured_applications_are_listed(make_env_file: EnvFileFactory) -> None:
    raw = (
        '[{"id":"lab","name":"Bir","base_url":"http://127.0.0.1:8100/"},'
        '{"id":"lab_ikinci","name":"İki","base_url":"http://127.0.0.1:8101/"}]'
    )
    apps = load_settings(make_env_file(AUTOMATION_APPLICATIONS_JSON=raw)).automation_applications_json
    assert [(a.id, a.name, a.origin) for a in apps] == [
        ("lab", "Bir", "http://127.0.0.1:8100"),
        ("lab_ikinci", "İki", "http://127.0.0.1:8101"),
    ]


def test_quotes_are_stripped_from_dotenv_but_kept_in_process_env(
    make_env_file: EnvFileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    quoted = '\'["http://127.0.0.1:8100","http://127.0.0.1:8101"]\''
    # dotenv dosyası: tırnaklar okuma sırasında kaldırılır → geçerli.
    assert load_settings(make_env_file(TARGET_ALLOWED_ORIGINS=quoted)).target_allowed_origins == [
        "http://127.0.0.1:8100",
        "http://127.0.0.1:8101",
    ]
    # Doğrudan ortam değişkeni: tırnak değerin parçasıdır → açık, redakte yapılandırma hatası.
    monkeypatch.setenv("TARGET_ALLOWED_ORIGINS", quoted)
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file())
    problems = _problems(exc)
    assert "TARGET_ALLOWED_ORIGINS" in problems and "JSON" in problems
    assert "127.0.0.1:8101" not in problems


def test_empty_application_list_is_valid_and_adds_nothing(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(AUTOMATION_APPLICATIONS_JSON="[]"))
    assert settings.automation_applications_json == ()


def test_application_list_is_required(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(AUTOMATION_APPLICATIONS_JSON=None))
    assert "AUTOMATION_APPLICATIONS_JSON: zorunlu ayar eksik veya boş" in _problems(exc)


_APP = '{"id":"lab","name":"Deney","base_url":"http://127.0.0.1:8100/"}'


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("[{bozuk", "geçerli JSON olmalı"),
        ('{"id":"lab"}', "JSON liste olmalı"),
        (f"[{_APP},{_APP}]", "2. kayıttaki id daha önce kullanılmış"),
        (
            '[{"id":"lab","name":"   ","base_url":"http://127.0.0.1:8100/"}]',
            "AUTOMATION_APPLICATIONS_JSON.0.NAME: boş olamaz",
        ),
        (
            '[{"id":"lab","base_url":"http://127.0.0.1:8100/"}]',
            "AUTOMATION_APPLICATIONS_JSON.0.NAME: zorunlu",
        ),
        (
            '[{"id":"Lab X","name":"A","base_url":"http://127.0.0.1:8100/"}]',
            "AUTOMATION_APPLICATIONS_JSON.0.ID",
        ),
        ('[{"id":"lab","name":"A","base_url":"ftp://127.0.0.1:8100/"}]', "base_url http(s)://host"),
        ('[{"id":"lab","name":"A","base_url":"yanlis-adres"}]', "base_url http(s)://host"),
        (
            '[{"id":"lab","name":"A","base_url":"http://u:gizli-parola@127.0.0.1:8100/"}]',
            "kimlik bilgisi içeremez",
        ),
        (
            '[{"id":"lab","name":"A","base_url":"http://127.0.0.1:8100/","extra":1}]',
            "bilinmeyen ayar anahtarı",
        ),
        (
            '[{"id":"lab","name":"A","base_url":"https://keyfi.example.org/"}]',
            "1. kaydın base_url origin'i TARGET_ALLOWED_ORIGINS içinde olmalı",
        ),
        (
            '[{"id":"opera","name":"Opera","base_url":"http://127.0.0.1:8100/"}]',
            "CATALOG_APPLICATION_ID, AUTOMATION_APPLICATIONS_JSON içindeki bir id olmalı",
        ),
    ],
)
def test_invalid_application_list_is_explicit_and_redacted(
    make_env_file: EnvFileFactory, raw: str, fragment: str
) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(AUTOMATION_APPLICATIONS_JSON=raw))
    problems = _problems(exc)
    assert fragment in problems
    assert "gizli-parola" not in problems and "keyfi.example.org" not in problems


S3_OK = {
    "ARTIFACT_BACKEND": "s3",
    "S3_ENDPOINT_URL": "https://s3.kurum.local",
    "S3_BUCKET": "agentask-kanit",
    "S3_REGION": "tr-ankara-1",
    "S3_ACCESS_KEY_ID": "AKIDTEST",
    "S3_SECRET_ACCESS_KEY": "test-secret-not-real",
}


def test_s3_backend_requires_complete_tls_configuration(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(make_env_file(**S3_OK))
    assert settings.artifact_backend.value == "s3" and "test-secret" not in repr(settings)
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{**S3_OK, "S3_BUCKET": None, "S3_SECRET_ACCESS_KEY": None}))
    assert "S3_BUCKET" in _problems(exc) and "S3_SECRET_ACCESS_KEY" in _problems(exc)
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{**S3_OK, "S3_ENDPOINT_URL": "http://s3.kurum.local"}))
    assert "https" in _problems(exc)
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(**{**S3_OK, "S3_ENDPOINT_URL": "https://u:p@s3.kurum.local"}))
    assert "kimlik bilgisi" in _problems(exc)
    assert load_settings(make_env_file(**{**S3_OK, "S3_ENDPOINT_URL": "http://127.0.0.1:9000"}))


def test_mongo_artifact_index_requires_mongo_catalog(make_env_file: EnvFileFactory) -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(make_env_file(ARTIFACT_INDEX_BACKEND="mongo", CATALOG_BACKEND="disabled"))
    assert "ARTIFACT_INDEX_BACKEND=mongo" in _problems(exc)

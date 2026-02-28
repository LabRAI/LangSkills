from __future__ import annotations

import json
import os
from pathlib import Path

from .env import load_master_config, load_runtime_env
from .utils.paths import repo_root

# This is a direct, data-only port of the original domain configuration.
# Keep it simple: override via config/langskills.json (domain_config) or config/source_content.json.

DEFAULT_DOMAIN_CONFIG: dict[str, dict] = {
    "linux": {
        "display_name": "Linux",
        "default_topic": "linux",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://man7.org/linux/man-pages/man1/find.1.html",
            "https://man7.org/linux/man-pages/man1/grep.1.html",
            "https://man7.org/linux/man-pages/man1/sed.1.html",
            "https://man7.org/linux/man-pages/man1/awk.1p.html",
            "https://man7.org/linux/man-pages/man1/tar.1.html",
            "https://man7.org/linux/man-pages/man1/rsync.1.html",
            "https://man7.org/linux/man-pages/man1/curl.1.html",
            "https://man7.org/linux/man-pages/man1/ssh.1.html",
            "https://www.freedesktop.org/software/systemd/man/latest/journalctl.html",
            "https://www.freedesktop.org/software/systemd/man/latest/systemctl.html",
            "https://man7.org/linux/man-pages/man1/xargs.1.html",
            "https://man7.org/linux/man-pages/man1/ps.1.html",
        ],
        "github": {"query": "linux cli", "min_stars": 200},
        "forum": {"tagged": "linux", "query": "linux command line"},
    },
    "devtools": {
        "display_name": "DevTools",
        "default_topic": "git",
        "crawl": {
            "webpage": {
                "allow_hosts": [],
                "deny_hosts": [],
            },
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://git-scm.com/docs/git-bisect",
            "https://git-scm.com/docs/git-rebase",
            "https://git-scm.com/docs/git-worktree",
            "https://git-scm.com/docs/git-stash",
            "https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions",
            "https://docs.github.com/en/actions/learn-github-actions/understanding-github-actions",
            "https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows",
            "https://docs.npmjs.com/cli/v10/commands/npm-run-script",
            "https://docs.python.org/3/tutorial/venv.html",
            "https://developer.mozilla.org/en-US/docs/Learn/Tools_and_testing/Understanding_client-side_tools/Overview",
            "https://git-scm.com/docs/git-merge",
            "https://docs.npmjs.com/cli/v10/commands/npm-ci",
        ],
        "github": {"query": "topic:git", "min_stars": 200},
        "forum": {"tagged": "git", "query": "developer workflow"},
    },
    "cloud": {
        "display_name": "Cloud",
        "default_topic": "kubernetes",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/",
            "https://kubernetes.io/docs/reference/kubectl/generated/kubectl_config/",
            "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
            "https://kubernetes.io/docs/concepts/services-networking/service/",
            "https://kubernetes.io/docs/concepts/configuration/configmap/",
            "https://kubernetes.io/docs/concepts/configuration/secret/",
            "https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/",
            "https://kubernetes.io/docs/concepts/policy/resource-quotas/",
            "https://kubernetes.io/docs/tasks/debug/debug-application/",
            "https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/",
            "https://kubernetes.io/docs/concepts/cluster-administration/logging/",
            "https://kubernetes.io/docs/tasks/tools/",
        ],
        "github": {"query": "kubernetes", "min_stars": 200},
        "forum": {"tagged": "kubernetes", "query": "kubernetes troubleshooting"},
    },
    "data": {
        "display_name": "Data",
        "default_topic": "duckdb",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://duckdb.org/docs/guides/import/csv_import.html",
            "https://duckdb.org/docs/guides/import/parquet_import.html",
            "https://duckdb.org/docs/data/parquet/overview.html",
            "https://duckdb.org/docs/sql/window_functions.html",
            "https://duckdb.org/docs/sql/introduction.html",
            "https://duckdb.org/docs/guides/overview.html",
            "https://www.postgresql.org/docs/current/using-explain.html",
            "https://www.postgresql.org/docs/current/indexes.html",
            "https://pandas.pydata.org/docs/user_guide/groupby.html",
            "https://sqlite.org/windowfunctions.html",
            "https://duckdb.org/docs/guides/file_formats/overview.html",
            "https://duckdb.org/docs/data/csv/overview.html",
        ],
        "github": {"query": "duckdb", "min_stars": 200},
        "forum": {"tagged": "duckdb", "query": ""},
    },
    "security": {
        "display_name": "Security",
        "default_topic": "security",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://owasp.org/www-project-top-ten/",
            "https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html",
            "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63-3.pdf",
            "https://man.openbsd.org/sshd_config",
            "https://ssl-config.mozilla.org/",
        ],
        "github": {"query": "owasp security", "min_stars": 200},
        "forum": {"tagged": "security;owasp;oauth;jwt;tls;xss;csrf", "query": "web security authentication"},
    },
    "observability": {
        "display_name": "Observability",
        "default_topic": "observability",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://prometheus.io/docs/introduction/overview/",
            "https://prometheus.io/docs/concepts/data_model/",
            "https://prometheus.io/docs/prometheus/latest/querying/basics/",
            "https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/",
            "https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/",
            "https://grafana.com/docs/grafana/latest/dashboards/",
            "https://grafana.com/docs/grafana/latest/alerting/",
            "https://opentelemetry.io/docs/concepts/signals/",
            "https://opentelemetry.io/docs/specs/semconv/",
            "https://opentelemetry.io/docs/concepts/signals/traces/",
            "https://opentelemetry.io/docs/concepts/signals/metrics/",
            "https://opentelemetry.io/docs/concepts/signals/logs/",
            "https://www.jaegertracing.io/docs/latest/",
            "https://grafana.com/docs/tempo/latest/",
        ],
        "github": {"query": "opentelemetry", "min_stars": 200},
        "forum": {"tagged": "opentelemetry;prometheus;grafana;jaeger", "query": "tracing metrics logging alerting"},
    },
    "web": {
        "display_name": "Web",
        "default_topic": "web",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            # MDN
            "https://developer.mozilla.org/en-US/docs/Web/HTTP",
            "https://developer.mozilla.org/en-US/docs/Web/API",
            "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch",
            "https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API",
            "https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API",
            "https://developer.mozilla.org/en-US/docs/Web/API/WebSocket",
            "https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API",
            "https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API",
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules",
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise",
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function",
            "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout",
            "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_flexible_box_layout",
            "https://developer.mozilla.org/en-US/docs/Web/CSS/container_queries",
            "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS",
            "https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP",
            "https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching",
            "https://developer.mozilla.org/en-US/docs/Web/Performance",
            "https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA",
            # React
            "https://react.dev/reference/react",
            "https://react.dev/reference/react/hooks",
            "https://react.dev/reference/react/useState",
            "https://react.dev/reference/react/useEffect",
            "https://react.dev/reference/react/useContext",
            "https://react.dev/reference/react/useMemo",
            "https://react.dev/reference/react/useCallback",
            "https://react.dev/reference/react/useRef",
            "https://react.dev/reference/react/Suspense",
            "https://react.dev/learn",
            "https://react.dev/learn/thinking-in-react",
            "https://react.dev/learn/managing-state",
            # Next.js
            "https://nextjs.org/docs/app",
            "https://nextjs.org/docs/app/building-your-application/routing",
            "https://nextjs.org/docs/app/building-your-application/data-fetching",
            "https://nextjs.org/docs/app/building-your-application/rendering",
            "https://nextjs.org/docs/app/building-your-application/caching",
            "https://nextjs.org/docs/app/building-your-application/optimizing",
            "https://nextjs.org/docs/app/api-reference/functions/fetch",
            # Vue
            "https://vuejs.org/guide/essentials/reactivity-fundamentals.html",
            "https://vuejs.org/guide/essentials/computed.html",
            "https://vuejs.org/guide/components/props.html",
            "https://vuejs.org/guide/reusability/composables.html",
            "https://vuejs.org/guide/scaling-up/state-management.html",
            # TypeScript
            "https://www.typescriptlang.org/docs/handbook/intro.html",
            "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/generics.html",
            "https://www.typescriptlang.org/docs/handbook/2/narrowing.html",
            "https://www.typescriptlang.org/docs/handbook/2/mapped-types.html",
            "https://www.typescriptlang.org/docs/handbook/2/conditional-types.html",
            "https://www.typescriptlang.org/docs/handbook/utility-types.html",
            # Node.js
            "https://nodejs.org/docs/latest/api/stream.html",
            "https://nodejs.org/docs/latest/api/events.html",
            "https://nodejs.org/docs/latest/api/fs.html",
            "https://nodejs.org/docs/latest/api/worker_threads.html",
            "https://nodejs.org/docs/latest/api/crypto.html",
            "https://nodejs.org/docs/latest/api/http.html",
            # Web Performance
            "https://web.dev/learn/performance/",
            "https://web.dev/articles/vitals",
            "https://web.dev/articles/lcp",
            "https://web.dev/articles/cls",
            "https://web.dev/articles/inp",
            "https://web.dev/learn/accessibility/",
            # Vite / Build Tools
            "https://vite.dev/guide/",
            "https://vite.dev/config/",
            "https://webpack.js.org/concepts/",
            "https://esbuild.github.io/api/",
            # Testing
            "https://jestjs.io/docs/getting-started",
            "https://vitest.dev/guide/",
            "https://testing-library.com/docs/react-testing-library/intro/",
            "https://playwright.dev/docs/intro",
            # CSS Frameworks
            "https://tailwindcss.com/docs/utility-first",
            "https://tailwindcss.com/docs/responsive-design",
            # GraphQL
            "https://graphql.org/learn/",
            "https://graphql.org/learn/schema/",
            # Security
            "https://owasp.org/www-project-web-security-testing-guide/",
            "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Scripting_Prevention_Cheat_Sheet.html",
            "https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html",
            # Express / Fastify
            "https://expressjs.com/en/guide/routing.html",
            "https://expressjs.com/en/guide/error-handling.html",
            "https://fastify.dev/docs/latest/Guides/Getting-Started/",
            # Prisma
            "https://www.prisma.io/docs/getting-started",
            "https://www.prisma.io/docs/concepts/components/prisma-client/crud",
            # Angular
            "https://angular.dev/guide/signals",
            "https://angular.dev/guide/di",
            # Svelte
            "https://svelte.dev/docs/introduction",
            "https://kit.svelte.dev/docs/introduction",
            # Deno
            "https://docs.deno.com/runtime/fundamentals/",
            # PWA
            "https://web.dev/articles/progressive-web-apps",
        ],
        "github": {"query": "", "min_stars": 500},
        "forum": {"tagged": "javascript", "query": ""},
    },
    "ml": {
        "display_name": "ML",
        "default_topic": "ml",
        "crawl": {
            "webpage": {"allow_hosts": [], "deny_hosts": []},
            "github": {"allow_hosts": ["github.com"], "deny_hosts": []},
            "forum": {"allow_hosts": ["stackoverflow.com"], "deny_hosts": []},
        },
        "web_urls": [
            "https://pytorch.org/docs/stable/index.html",
            "https://pytorch.org/docs/stable/amp.html",
            "https://pytorch.org/docs/stable/distributed.html",
            "https://pytorch.org/tutorials/beginner/saving_loading_models.html",
            "https://huggingface.co/docs/transformers/index",
            "https://huggingface.co/docs/transformers/main_classes/trainer",
            "https://huggingface.co/docs/datasets/index",
            "https://huggingface.co/docs/peft/index",
            "https://scikit-learn.org/stable/modules/model_evaluation.html",
            "https://scikit-learn.org/stable/modules/cross_validation.html",
            "https://mlflow.org/docs/latest/tracking.html",
            "https://mlflow.org/docs/latest/model-registry.html",
            "https://faiss.ai/",
        ],
        "github": {"query": "transformers lora finetune", "min_stars": 200},
        "forum": {"tagged": "pytorch;huggingface-transformers;scikit-learn;mlflow;faiss", "query": "training distributed amp checkpoint"},
    },
}


def _load_domain_config_from_file(path: Path) -> dict[str, dict] | None:
    try:
        raw = path.read_text()
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def load_domain_config() -> dict[str, dict]:
    root = repo_root()
    master = load_master_config(root) or {}
    for key in ("domain_config", "source_content"):
        block = master.get(key) if isinstance(master, dict) else None
        if isinstance(block, dict) and block:
            return block
    override = str(os.environ.get("LANGSKILLS_DOMAIN_CONFIG") or "").strip()
    if not override:
        runtime_env = load_runtime_env(root)
        override = str(runtime_env.get("LANGSKILLS_DOMAIN_CONFIG") or "").strip()
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = root / p
        cfg = _load_domain_config_from_file(p)
        if cfg:
            return cfg

    default_path = root / "config" / "source_content.json"
    cfg = _load_domain_config_from_file(default_path)
    if cfg:
        return cfg
    return DEFAULT_DOMAIN_CONFIG


DOMAIN_CONFIG: dict[str, dict] = load_domain_config()

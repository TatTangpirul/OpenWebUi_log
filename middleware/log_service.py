"""
EKS log middleware — sits between OpenWebUI and the Kubernetes API.
Uses the official kubernetes python client (no kubectl subprocess).
"""
import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import subprocess

# Namespaces this middleware is allowed to touch. RBAC (RoleBinding per
# namespace) should mirror this list — do not widen this to a ClusterRole.
NAMESPACE_ALLOWLIST: list[str] = [
    "seven-deli-chat-stg",
    "seven-deli-chat-dev",
    "scp-cpall-rag-edge-stg",
    "scp-cpall-rag-edge-dev",
    "scp-cpall-rag-data-stg",
    "scp-cpall-rag-data-dev",
    "scp-cpall-rag-app-stg",
    "scp-cpall-rag-app-dev",
]

@dataclass
class DiscoverySnapshot:
    namespaces: dict[str, list[str]]  # namespace -> list of pod names
    updated_at: datetime


# Epoch updated_at means "never refreshed" -> any TTL check treats it as stale.
_discovery_cache = DiscoverySnapshot(
    namespaces={},
    updated_at=datetime.fromtimestamp(0, tz=timezone.utc),
)


def is_stale(snapshot: DiscoverySnapshot, max_age: timedelta = timedelta(days=1)) -> bool:
    return datetime.now(timezone.utc) - snapshot.updated_at > max_age


def _load_k8s_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


_load_k8s_config()
core_v1 = client.CoreV1Api()


def list_pods(namespace: str) -> list[str]:
    """
    List service names discoverable inside a single allow-listed namespace.
    Used to build/refresh a DiscoverySnapshot.

    :param namespace: must be a member of NAMESPACE_ALLOWLIST
    :return: service names found in that namespace
    """
    result = subprocess.run(["cmd/list_pods.sh", namespace], capture_output=True, text=True)
    pods = result.stdout.splitlines()
    _discovery_cache.namespaces[namespace] = pods
    _discovery_cache.updated_at = datetime.now(timezone.utc)
    return pods


def get_namespace_logs(namespace: str, minutes: int = 60) -> dict[str, Any]:
    """
    Fetch recent logs for every service/pod inside a single namespace
    ("system" with no specific service named).

    :param namespace: must be a member of NAMESPACE_ALLOWLIST
    :param minutes: lookback window
    :return: per-pod/service result, e.g.
        {"ok": True, "namespace": namespace, "results": {...}}
        or {"ok": False, "error": "..."}
    """
    if namespace not in _discovery_cache.namespaces or is_stale(_discovery_cache):
        list_pods(namespace)

    pods = _discovery_cache.namespaces[namespace]

    def fetch(pod: str) -> tuple[str, str]:
        result = subprocess.run(
            ["cmd/get_log.sh", pod, namespace, str(minutes)], capture_output=True, text=True
        )
        return pod, result.stdout

    logs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(pods), 8) or 1) as pool:
        for pod, output in pool.map(fetch, pods):
            logs[pod] = output

    return {"ok": True, "namespace": namespace, "results": logs}


def _unwrap_bytes_repr(log: str) -> str:
    """
    kubernetes-client quirk, verified against this cluster (kubernetes==36.0.2): every
    read_namespaced_pod_log body — empty or not — comes back as str(<bytes>) instead of a
    properly-decoded string, e.g. "b'INFO: ...\\n...'" with escaped newlines, rather than
    the real text with real newlines. ast.literal_eval reverses exactly what str(bytes)
    produced (undoing the \\n/\\t/quote escaping per Python bytes-literal syntax), then we
    decode the recovered bytes as UTF-8 to get the real log text back.
    """
    if log.startswith("b'") and log.endswith("'"):
        return ast.literal_eval(log).decode("utf-8")
    return log


def get_pod_logs(namespace: str, service: str, minutes: int = 60) -> dict[str, Any]:
    """
    Fetch recent logs for one specific service (label-selected deployment)
    inside a namespace.

    :param namespace: must be a member of NAMESPACE_ALLOWLIST
    :param service: used to build the pod label selector, e.g. app=<service>
    :param minutes: lookback window
    :return: per-pod result, e.g.
        {"ok": True, "namespace": namespace, "service": service, "results": {...}}
        or {"ok": False, "error": "..."}
    """
    if namespace not in NAMESPACE_ALLOWLIST:
        return {"ok": False, "error": f"Namespace '{namespace}' is not allow-listed"}

    try:
        all_pods = core_v1.list_namespaced_pod(namespace).items
    except ApiException as e:
        return {"ok": False, "error": f"Failed to list pods in namespace '{namespace}': {e.reason}"}

    # Not every chart in this cluster labels pods the same way: some Helm charts set
    # app.kubernetes.io/name to the service name directly; others (e.g. the 7deli-rag-api
    # chart backing rag-api-sod/rag-api-hr) share one chart-wide name and instead
    # distinguish services via app.kubernetes.io/component. Legacy app= is also still seen.
    # Checked against real pods in seven-deli-chat-dev before picking these three keys.
    pods = [
        pod
        for pod in all_pods
        if service
        in (
            (pod.metadata.labels or {}).get("app.kubernetes.io/component"),
            (pod.metadata.labels or {}).get("app.kubernetes.io/name"),
            (pod.metadata.labels or {}).get("app"),
        )
    ]

    if not pods:
        return {"ok": False, "error": f"No pods found for service '{service}' in namespace '{namespace}'"}

    def fetch(pod_name: str) -> tuple[str, str]:
        try:
            log = core_v1.read_namespaced_pod_log(
                name=pod_name, namespace=namespace, since_seconds=minutes * 60
            )
            log = _unwrap_bytes_repr(log)
        except ApiException as e:
            log = f"<error fetching logs: {e.reason}>"
        return pod_name, log

    pod_names = [pod.metadata.name for pod in pods]
    logs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(pod_names), 8)) as pool:
        for pod_name, output in pool.map(fetch, pod_names):
            logs[pod_name] = output

    return {"ok": True, "namespace": namespace, "service": service, "results": logs}
